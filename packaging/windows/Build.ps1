#!/usr/bin/env pwsh
param(
    [string]$Configuration = "Release",
    [string]$RuntimeIdentifier = "win-x64",
    [string]$BuildRoot = "build/windows",
    [string]$Version = "",
    [string]$Manufacturer = "HammerHeads Engineers Sp. z o.o.",
    [string]$ProductName = "SPX",
    [string]$BundleName = "SPX Setup",
    [string]$SignThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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

function Invoke-SignTool {
    param(
        [string]$Path,
        [string]$Thumbprint,
        [string]$TimestampUrl
    )

    if (-not $Thumbprint) {
        return
    }

    Need-Command "signtool"
    Invoke-Process -FileName "signtool" -WorkingDirectory $RepoRoot -Arguments @(
        "sign",
        "/fd",
        "SHA256",
        "/td",
        "SHA256",
        "/tr",
        $TimestampUrl,
        "/sha1",
        $Thumbprint,
        $Path
    )
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

$BuildRootPath = Join-Path $RepoRoot $BuildRoot
$PayloadStageDir = Join-Path $BuildRootPath "stage\install"
$LauncherPublishDir = Join-Path $BuildRootPath "publish\launcher"
$PayloadManifestPath = Join-Path $BuildRootPath "payload-manifest.json"
$PayloadFragmentPath = Join-Path $BuildRootPath "Payload.wxs"
$ArtifactsDir = Join-Path $BuildRootPath "artifacts"
$LauncherProjectPath = Join-Path $RepoRoot "packaging\windows\launcher\SpxLauncher.csproj"
$LicenseFilePath = Join-Path $RepoRoot "packaging\windows\LICENSE.rtf"

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
if (Test-Path $PayloadStageDir) {
    Remove-Item -Recurse -Force $PayloadStageDir
}
if (Test-Path $LauncherPublishDir) {
    Remove-Item -Recurse -Force $LauncherPublishDir
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

Invoke-SignTool -Path (Join-Path $LauncherPublishDir "SpxLauncher.exe") -Thumbprint $SignThumbprint -TimestampUrl $TimestampUrl

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
$BundleOutputPath = Join-Path $ArtifactsDir ("spx-setup-{0}.exe" -f $Version)
$ProductWxsPath = Join-Path $RepoRoot "packaging\windows\wix\SPX.Product.wxs"
$BundleWxsPath = Join-Path $RepoRoot "packaging\windows\wix\SPX.Bundle.wxs"

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
    "ProductName=$ProductName"
)

Invoke-SignTool -Path $MsiOutputPath -Thumbprint $SignThumbprint -TimestampUrl $TimestampUrl

Invoke-Process -FileName $WixCommand -WorkingDirectory $RepoRoot -Arguments @(
    "build",
    $BundleWxsPath,
    "-ext",
    "WixToolset.BootstrapperApplications.wixext",
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
    "MsiPath=$MsiOutputPath"
)

Invoke-SignTool -Path $BundleOutputPath -Thumbprint $SignThumbprint -TimestampUrl $TimestampUrl

Write-Host ""
Write-Host "Windows installer artifacts:"
Write-Host "  MSI:    $MsiOutputPath"
Write-Host "  Bundle: $BundleOutputPath"
Write-Host "  Stage:  $PayloadStageDir"
Write-Host "  WiX:    $PayloadFragmentPath"
