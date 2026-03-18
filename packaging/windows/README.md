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
- generates a WiX fragment for the staged files,
- builds an MSI that installs the payload under `Program Files\SPX`,
- builds a Burn bundle EXE that chains the MSI.

The current scaffold does not yet bundle prerequisites such as Python or Docker. `SpxLauncher.exe` still delegates into the existing PowerShell/Python flows after installation.

## Prerequisites

- .NET SDK 8.0+
- WiX Toolset v6 CLI on `PATH`
- Poetry environment for this repository
- `signtool` plus a public-trust code-signing certificate if you want signed artifacts

Installer builds normalize repository semver into Windows-friendly numeric versions. The MSI uses `major.minor.patch`; the Burn bundle carries `major.minor.patch.revision` when the repo version ends with a numeric prerelease suffix such as `-rc.24`.

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
  -SignThumbprint YOUR_CERT_THUMBPRINT
```

Artifacts are written under `build/windows/artifacts/`.

## Next steps

- Add a Burn prerequisite chain for Python 3.12 and a clear Docker prerequisite UX.
- Decide whether the final install scope should stay `Program Files` per-machine or move to a per-user layout.
- Add a CI job that builds and signs the Windows artifacts on a trusted Windows runner.
