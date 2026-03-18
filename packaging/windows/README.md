# Windows Trusted Installer

This directory contains the first Windows-native installer scaffold for SPX:

- `Build.ps1` stages the installer payload, publishes the Windows launcher, builds the MSI, and wraps it in a WiX Burn bundle EXE.
- `launcher/` contains `SpxLauncher.exe`, the user-facing entrypoint for `setup`, `mcp-setup`, `start`, `stop`, and `cleanup`.
- `wix/` contains the WiX source consumed by WiX Toolset v6 for the MSI and Burn bundle.

## Goals

- Keep `origin/develop` as the source of truth for the payload and installer logic.
- Present a signed `SPX Setup.exe` / `SPX.msi` workflow on Windows instead of exposing `.bat` and `.ps1` directly.
- Reuse the existing Python installer CLI and MCP workspace bootstrap instead of forking product logic.

## Current shape

The current scaffold does the following:

- stages the same repo payload that ships in the portable installer package,
- publishes a self-contained `SpxLauncher.exe`,
- downloads or reuses a cached official Python 3.12 offline installer and verifies its Authenticode signature,
- generates a WiX fragment for the staged files,
- builds an MSI that installs the payload under `Program Files\SPX`,
- builds a Burn bundle EXE that chains the Python prerequisite and the MSI.

The current scaffold still does not install Docker. `SpxLauncher.exe` delegates into the existing PowerShell/Python flows after installation, but `setup` now exports `PYTHON_BIN` explicitly so the installed flow uses the resolved Python interpreter instead of relying on `PATH` ordering.

## Prerequisites

- .NET SDK 8.0+
- WiX Toolset v6 CLI on `PATH`
- Poetry environment for this repository
- `signtool` plus either a public-trust code-signing certificate or Azure Trusted Signing inputs if you want signed artifacts

Installer builds normalize repository semver into Windows-friendly numeric versions. The MSI uses `major.minor.patch`; the Burn bundle carries `major.minor.patch.revision` when the repo version ends with a numeric prerelease suffix such as `-rc.24`.

The Burn bundle defaults to Python `3.12.10`, which is the last Python 3.12 release that still ships the classic Windows offline installer. You can override the cached installer path or URL if you need a different payload.

Quick install via `winget`:

```powershell
winget install --id Microsoft.DotNet.SDK.8 --exact --source winget
winget install --id WiXToolset.WiXCLI --exact --source winget
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\Build.ps1
```

Useful options:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\Build.ps1 `
  -Configuration Release `
  -RuntimeIdentifier win-x64 `
  -PythonInstallerPath C:\cache\python-3.12.10-amd64.exe `
  -SignThumbprint YOUR_CERT_THUMBPRINT
```

Artifacts are written under `build/windows/artifacts/`.

The Python prerequisite is cached under `build/windows/cache/` by default and is validated with `Get-AuthenticodeSignature` against the `Python Software Foundation` signer before WiX consumes it.

## Signing

Classic certificate signing:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\Build.ps1 `
  -SignThumbprint YOUR_CERT_THUMBPRINT
```

Azure Trusted Signing:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\Build.ps1 `
  -TrustedSigningDlibPath C:\signing\Azure.CodeSigning.Dlib.dll `
  -TrustedSigningMetadataPath C:\signing\metadata.json `
  -SignToolPath "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
```

Trusted Signing expects a modern Windows SDK `signtool.exe` and the build script switches the default timestamp service to `http://timestamp.acs.microsoft.com/` when that mode is active.

## Next steps

- Add a clearer Docker Desktop prerequisite UX in the bootstrapper and launcher.
- Decide whether the final install scope should stay `Program Files` per-machine or move to a per-user layout.
- Add a CI job that builds and signs the Windows artifacts on a trusted Windows runner.
