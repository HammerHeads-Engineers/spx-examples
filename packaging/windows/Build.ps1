#!/usr/bin/env pwsh
# SPDX-License-Identifier: MIT
param(
    [string]$Configuration = "Release",
    [string]$RuntimeIdentifier = "win-x64",
    [string]$BuildRoot = "build/windows",
    [string]$Version = "",
    [string]$Manufacturer = "HammerHeads Engineers Sp. z o.o.",
    [string]$ProductName = "SPX Tools",
    [string]$BundleName = "SPX Tools",
    [string]$PythonVersion = "3.12.10",
    [string]$PythonInstallerPath = "",
    [string]$PythonInstallerUrl = "",
    [string]$PythonPackageDisplayName = "",
    [string]$SignThumbprint = "",
    [string]$SignToolPath = "",
    [string]$TrustedSigningDlibPath = "",
    [string]$TrustedSigningMetadataPath = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$TrustedSigningMinimumSignToolVersion = [version]"10.0.22621.755"
$TrustedSigningTimestampUrl = "http://timestamp.acs.microsoft.com/"
$PythonInstallerSigner = "Python Software Foundation"

function Need-Command {
    param([string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Command"
    }
}

function Assert-DotNetSdk {
    $sdks = & dotnet --list-sdks
    if ($LASTEXITCODE -ne 0 -or -not $sdks) {
        throw ".NET SDK 8.0+ is required to build the Windows launcher."
    }
}

function Resolve-WixCommand {
    $command = Get-Command "wix" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = "C:\Program Files\WiX Toolset v6.0\bin\wix.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "Missing required command: wix"
}

function Resolve-SignToolCommand {
    param([string]$PreferredPath)

    if ($PreferredPath) {
        if (-not (Test-Path $PreferredPath -PathType Leaf)) {
            throw "SignTool was not found at '$PreferredPath'."
        }
        return (Resolve-Path $PreferredPath).Path
    }

    $command = Get-Command "signtool" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $kitsRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $kitsRoot) {
        $sdkBins = Get-ChildItem -Path $kitsRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object { [version]$_.Name } -Descending
        foreach ($sdkBin in $sdkBins) {
            $candidate = Join-Path $sdkBin.FullName "x64\signtool.exe"
            if (Test-Path $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }

    throw "Unable to locate signtool.exe. Install the Windows SDK or pass -SignToolPath."
}

function Get-SignToolVersion {
    param([string]$Path)

    $item = Get-Item $Path
    return [version]::new(
        $item.VersionInfo.FileMajorPart,
        $item.VersionInfo.FileMinorPart,
        $item.VersionInfo.FileBuildPart,
        $item.VersionInfo.FilePrivatePart
    )
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-RepoVersion {
    param([string]$RepoRoot)

    $pyprojectPath = Join-Path $RepoRoot "pyproject.toml"
    $match = Select-String -Path $pyprojectPath -Pattern '^version = "([^"]+)"$' | Select-Object -First 1
    if (-not $match) {
        throw "Unable to resolve version from $pyprojectPath"
    }

    return $match.Matches[0].Groups[1].Value
}

function Get-WindowsVersionInfo {
    param([string]$Version)

    $match = [regex]::Match($Version, '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)(?:[-+](?<suffix>.+))?$')
    if (-not $match.Success) {
        throw "Unable to derive Windows installer version from '$Version'"
    }

    $major = [int]$match.Groups["major"].Value
    $minor = [int]$match.Groups["minor"].Value
    $patch = [int]$match.Groups["patch"].Value
    $revision = 0
    $suffix = $match.Groups["suffix"].Value
    if ($suffix) {
        $suffixNumber = [regex]::Match($suffix, '(\d+)(?!.*\d)')
        if ($suffixNumber.Success) {
            $revision = [int]$suffixNumber.Groups[1].Value
        }
    }

    if ($major -gt 255 -or $minor -gt 255 -or $patch -gt 65535) {
        throw "Windows installer version components exceed MSI limits: '$Version'"
    }

    return @{
        PackageVersion = "$major.$minor.$patch"
        BundleVersion = "$major.$minor.$patch.$revision"
    }
}

function Get-SigningMode {
    param(
        [string]$Thumbprint,
        [string]$TrustedSigningDlibPath,
        [string]$TrustedSigningMetadataPath
    )

    $hasTrustedSigningInput = -not [string]::IsNullOrWhiteSpace($TrustedSigningDlibPath) -or
        -not [string]::IsNullOrWhiteSpace($TrustedSigningMetadataPath)

    if ($Thumbprint -and $hasTrustedSigningInput) {
        throw "Choose one signing mode: either -SignThumbprint or Trusted Signing inputs."
    }

    if ($hasTrustedSigningInput) {
        if ([string]::IsNullOrWhiteSpace($TrustedSigningDlibPath) -or [string]::IsNullOrWhiteSpace($TrustedSigningMetadataPath)) {
            throw "Trusted Signing requires both -TrustedSigningDlibPath and -TrustedSigningMetadataPath."
        }

        return "trusted"
    }

    if (-not [string]::IsNullOrWhiteSpace($Thumbprint)) {
        return "thumbprint"
    }

    return "none"
}

function Resolve-RequiredFile {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "$Label was not found at '$Path'."
    }

    return (Resolve-Path $Path).Path
}

function Invoke-Process {
    param(
        [string]$FileName,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    Write-Host "[$FileName] $($Arguments -join ' ')"
    & $FileName @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FileName failed with exit code $LASTEXITCODE"
    }
}

function Assert-AuthenticodeSigner {
    param(
        [string]$Path,
        [string]$ExpectedSubject
    )

    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status -ne "Valid") {
        throw "Authenticode verification failed for '$Path' with status '$($signature.Status)'."
    }

    $subject = $signature.SignerCertificate.Subject
    if ($subject -notlike "*$ExpectedSubject*") {
        throw "Unexpected signer for '$Path': '$subject'. Expected '$ExpectedSubject'."
    }

    $sha256 = (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    Write-Host "[verify] Authenticode signer '$ExpectedSubject'; SHA256 $sha256"
}

function Resolve-PythonInstallerUrl {
    param(
        [string]$PythonVersion,
        [string]$PythonInstallerUrl
    )

    if ($PythonInstallerUrl) {
        return $PythonInstallerUrl
    }

    return "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
}

function Resolve-PythonInstallerArtifact {
    param(
        [string]$BuildRootPath,
        [string]$PythonVersion,
        [string]$PythonInstallerPath,
        [string]$PythonInstallerUrl
    )

    if ($PythonInstallerPath) {
        $resolvedPath = Resolve-RequiredFile -Path $PythonInstallerPath -Label "Python installer"
        Assert-AuthenticodeSigner -Path $resolvedPath -ExpectedSubject $PythonInstallerSigner
        return $resolvedPath
    }

    $downloadUrl = Resolve-PythonInstallerUrl -PythonVersion $PythonVersion -PythonInstallerUrl $PythonInstallerUrl
    $cacheDir = Join-Path $BuildRootPath "cache"
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

    $uri = [uri]$downloadUrl
    $fileName = Split-Path $uri.AbsolutePath -Leaf
    if (-not $fileName) {
        throw "Unable to derive a Python installer filename from '$downloadUrl'."
    }

    $downloadPath = Join-Path $cacheDir $fileName
    if (-not (Test-Path $downloadPath -PathType Leaf)) {
        Write-Host "[download] $downloadUrl -> $downloadPath"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $downloadPath -UseBasicParsing
    }
    else {
        Write-Host "[download] Reusing cached Python installer $downloadPath"
    }

    try {
        Assert-AuthenticodeSigner -Path $downloadPath -ExpectedSubject $PythonInstallerSigner
    }
    catch {
        if (Test-Path $downloadPath -PathType Leaf) {
            Remove-Item -Force $downloadPath
        }
        throw
    }

    return (Resolve-Path $downloadPath).Path
}

function Invoke-SignTool {
    param(
        [string]$Path,
        [string]$SigningMode,
        [string]$SignToolCommand,
        [string]$Thumbprint,
        [string]$TimestampUrl,
        [string]$TrustedSigningDlibPath,
        [string]$TrustedSigningMetadataPath
    )

    if ($SigningMode -eq "none") {
        return
    }

    $arguments = @(
        "sign",
        "/fd",
        "SHA256",
        "/td",
        "SHA256",
        "/tr",
        $TimestampUrl
    )

    switch ($SigningMode) {
        "thumbprint" {
            $arguments += @("/sha1", $Thumbprint)
        }
        "trusted" {
            $arguments += @(
                "/dlib",
                $TrustedSigningDlibPath,
                "/dmdf",
                $TrustedSigningMetadataPath
            )
        }
        default {
            throw "Unsupported signing mode '$SigningMode'."
        }
    }

    $arguments += $Path
    Invoke-Process -FileName $SignToolCommand -WorkingDirectory $RepoRoot -Arguments $arguments
}

$RepoRoot = Get-RepoRoot
if (-not $Version) {
    $Version = Get-RepoVersion -RepoRoot $RepoRoot
}

$WindowsVersion = Get-WindowsVersionInfo -Version $Version
$PackageVersion = $WindowsVersion.PackageVersion
$BundleVersion = $WindowsVersion.BundleVersion

Need-Command "dotnet"
Need-Command "poetry"
Assert-DotNetSdk
$WixCommand = Resolve-WixCommand

$SigningMode = Get-SigningMode `
    -Thumbprint $SignThumbprint `
    -TrustedSigningDlibPath $TrustedSigningDlibPath `
    -TrustedSigningMetadataPath $TrustedSigningMetadataPath
$ResolvedSignToolPath = ""
if ($SigningMode -ne "none") {
    if ($SigningMode -eq "trusted" -and $TimestampUrl -eq "http://timestamp.digicert.com") {
        $TimestampUrl = $TrustedSigningTimestampUrl
    }

    $ResolvedSignToolPath = Resolve-SignToolCommand -PreferredPath $SignToolPath
    if ($SigningMode -eq "trusted") {
        $TrustedSigningDlibPath = Resolve-RequiredFile -Path $TrustedSigningDlibPath -Label "Trusted Signing dlib"
        $TrustedSigningMetadataPath = Resolve-RequiredFile -Path $TrustedSigningMetadataPath -Label "Trusted Signing metadata"

        $signToolVersion = Get-SignToolVersion -Path $ResolvedSignToolPath
        if ($signToolVersion -lt $TrustedSigningMinimumSignToolVersion) {
            throw "Trusted Signing requires signtool.exe $TrustedSigningMinimumSignToolVersion or newer. Resolved $ResolvedSignToolPath ($signToolVersion)."
        }
    }
}

$BuildRootPath = Join-Path $RepoRoot $BuildRoot
$PayloadStageDir = Join-Path $BuildRootPath "stage\install"
$LauncherPublishDir = Join-Path $BuildRootPath "publish\launcher"
$PayloadManifestPath = Join-Path $BuildRootPath "payload-manifest.json"
$PayloadFragmentPath = Join-Path $BuildRootPath "Payload.wxs"
$ArtifactsDir = Join-Path $BuildRootPath "artifacts"
$LauncherProjectPath = Join-Path $RepoRoot "packaging\windows\launcher\SpxLauncher.csproj"
$LicenseFilePath = Join-Path $RepoRoot "packaging\windows\LICENSE.rtf"
$ProductIconFilePath = Resolve-RequiredFile -Path (Join-Path $RepoRoot "packaging\windows\assets\spx.ico") -Label "Product icon"
$BundleLogoFilePath = Resolve-RequiredFile -Path (Join-Path $RepoRoot "packaging\windows\assets\spx.png") -Label "Bundle logo"
$BundleThemeFilePath = Resolve-RequiredFile -Path (Join-Path $RepoRoot "packaging\windows\wix\theme\RtfTheme.xml") -Label "Bundle theme"
$BundleThemeLocalizationFilePath = Resolve-RequiredFile -Path (Join-Path $RepoRoot "packaging\windows\wix\theme\RtfTheme.wxl") -Label "Bundle theme localization"
$ProductWxsPath = Join-Path $RepoRoot "packaging\windows\wix\SPX.Product.wxs"
$BundleWxsPath = Join-Path $RepoRoot "packaging\windows\wix\SPX.Bundle.wxs"

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
if (Test-Path $PayloadStageDir) {
    Remove-Item -Recurse -Force $PayloadStageDir
}
if (Test-Path $LauncherPublishDir) {
    Remove-Item -Recurse -Force $LauncherPublishDir
}

$ResolvedPythonInstallerPath = Resolve-PythonInstallerArtifact `
    -BuildRootPath $BuildRootPath `
    -PythonVersion $PythonVersion `
    -PythonInstallerPath $PythonInstallerPath `
    -PythonInstallerUrl $PythonInstallerUrl
if (-not $PythonPackageDisplayName) {
    $PythonPackageDisplayName = "Python $PythonVersion (64-bit)"
}

Invoke-Process -FileName "dotnet" -WorkingDirectory $RepoRoot -Arguments @(
    "publish",
    $LauncherProjectPath,
    "-c",
    $Configuration,
    "-r",
    $RuntimeIdentifier,
    "--self-contained",
    "true",
    "-p:PublishSingleFile=true",
    "-p:DebugType=None",
    "-o",
    $LauncherPublishDir
)

Invoke-SignTool `
    -Path (Join-Path $LauncherPublishDir "SpxLauncher.exe") `
    -SigningMode $SigningMode `
    -SignToolCommand $ResolvedSignToolPath `
    -Thumbprint $SignThumbprint `
    -TimestampUrl $TimestampUrl `
    -TrustedSigningDlibPath $TrustedSigningDlibPath `
    -TrustedSigningMetadataPath $TrustedSigningMetadataPath

Invoke-Process -FileName "poetry" -WorkingDirectory $RepoRoot -Arguments @(
    "run",
    "python",
    "tools/stage_windows_payload.py",
    "--output-dir",
    $PayloadStageDir,
    "--extra-path",
    $LauncherPublishDir,
    "--manifest-path",
    $PayloadManifestPath,
    "--wix-fragment",
    $PayloadFragmentPath
)

$MsiOutputPath = Join-Path $ArtifactsDir ("spx-windows-{0}.msi" -f $Version)
$BundleOutputPath = Join-Path $ArtifactsDir ("spx-installer-{0}.exe" -f $Version)

Invoke-Process -FileName $WixCommand -WorkingDirectory $RepoRoot -Arguments @(
    "build",
    $ProductWxsPath,
    $PayloadFragmentPath,
    "-arch",
    "x64",
    "-o",
    $MsiOutputPath,
    "-d",
    "PackageVersion=$PackageVersion",
    "-d",
    "Manufacturer=$Manufacturer",
    "-d",
    "ProductName=$ProductName",
    "-d",
    "ProductIconFile=$ProductIconFilePath"
)

Invoke-SignTool `
    -Path $MsiOutputPath `
    -SigningMode $SigningMode `
    -SignToolCommand $ResolvedSignToolPath `
    -Thumbprint $SignThumbprint `
    -TimestampUrl $TimestampUrl `
    -TrustedSigningDlibPath $TrustedSigningDlibPath `
    -TrustedSigningMetadataPath $TrustedSigningMetadataPath

Invoke-Process -FileName $WixCommand -WorkingDirectory $RepoRoot -Arguments @(
    "build",
    $BundleWxsPath,
    "-ext",
    "WixToolset.BootstrapperApplications.wixext",
    "-ext",
    "WixToolset.Util.wixext",
    "-arch",
    "x64",
    "-o",
    $BundleOutputPath,
    "-d",
    "BundleVersion=$BundleVersion",
    "-d",
    "Manufacturer=$Manufacturer",
    "-d",
    "BundleName=$BundleName",
    "-d",
    "LicenseFile=$LicenseFilePath",
    "-d",
    "BundleIconFile=$ProductIconFilePath",
    "-d",
    "ThemeFile=$BundleThemeFilePath",
    "-d",
    "ThemeLocalizationFile=$BundleThemeLocalizationFilePath",
    "-d",
    "LogoFile=$BundleLogoFilePath",
    "-d",
    "MsiPath=$MsiOutputPath",
    "-d",
    "PythonInstallerPath=$ResolvedPythonInstallerPath",
    "-d",
    "PythonPackageDisplayName=$PythonPackageDisplayName"
)

Invoke-SignTool `
    -Path $BundleOutputPath `
    -SigningMode $SigningMode `
    -SignToolCommand $ResolvedSignToolPath `
    -Thumbprint $SignThumbprint `
    -TimestampUrl $TimestampUrl `
    -TrustedSigningDlibPath $TrustedSigningDlibPath `
    -TrustedSigningMetadataPath $TrustedSigningMetadataPath

Write-Host ""
Write-Host "Windows installer artifacts:"
Write-Host "  MSI:              $MsiOutputPath"
Write-Host "  Bundle:           $BundleOutputPath"
Write-Host "  Stage:            $PayloadStageDir"
Write-Host "  WiX:              $PayloadFragmentPath"
Write-Host "  Python installer: $ResolvedPythonInstallerPath"
