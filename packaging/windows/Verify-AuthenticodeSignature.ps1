[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $Path,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $ExpectedSigner
)

$ErrorActionPreference = "Stop"

$windowsKitsBin = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$signtool = Get-ChildItem -LiteralPath $windowsKitsBin -Filter "signtool.exe" -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "[\\/]x64[\\/]signtool\.exe$" } |
    Sort-Object -Property { [version]$_.Directory.Parent.Name } -Descending |
    Select-Object -First 1

if ($null -eq $signtool) {
    throw "Could not find the x64 Windows SDK SignTool under '$windowsKitsBin'."
}

if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Cannot verify Authenticode signature because the file does not exist: '$Path'."
}

Write-Host "Verifying Authenticode signature for '$Path' with '$($signtool.FullName)'."
$verificationOutput = & $signtool.FullName verify /pa /all /v $Path 2>&1
$verificationExitCode = $LASTEXITCODE
$verificationReport = $verificationOutput -join [Environment]::NewLine
Write-Host $verificationReport

if ($verificationExitCode -ne 0) {
    throw "SignTool verification failed for '$Path' with exit code $verificationExitCode. See the verification report above."
}

if ($verificationReport -notmatch [regex]::Escape($ExpectedSigner)) {
    throw "The verified signatures for '$Path' do not include the expected publisher '$ExpectedSigner'."
}

Write-Host "Verified a valid Authenticode signature from '$ExpectedSigner' on '$Path'."
