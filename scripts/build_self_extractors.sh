#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_self_extractors.sh [--version VERSION] [--output-dir DIR]

Creates single-file self-extracting installers for Unix (.run) and PowerShell (.ps1)
based on the folder produced by scripts/build_installer_package.sh.

Options:
  --version VERSION   Version string used in generated filenames (default: dev)
  --output-dir DIR    Directory containing the base installer folder (default: dist)
EOF
}

VERSION="dev"
OUTPUT_DIR="dist"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

VERSION="${VERSION#v}"
if [[ -z "${VERSION}" || ! "${VERSION}" =~ ^[0-9A-Za-z][0-9A-Za-z.-]*$ ]]; then
  echo "Version must contain only letters, numbers, dots, and hyphens." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${OUTPUT_DIR}" = /* ]]; then
  DEST_DIR="${OUTPUT_DIR}"
else
  DEST_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi
BASE_DIR="${DEST_DIR}/spx-installer"

if [[ ! -d "${BASE_DIR}" ]]; then
  echo "[self-extract] Base installer directory not found at ${BASE_DIR}. Building it first..."
  "${REPO_ROOT}/scripts/build_installer_package.sh" --output-dir "${DEST_DIR}"
fi

RUN_FILE="${DEST_DIR}/spx-installer-${VERSION}.run"
PS1_FILE="${DEST_DIR}/spx-installer-${VERSION}.ps1"

tmp_tar="$(mktemp)"
tar -C "${DEST_DIR}" -czf "${tmp_tar}" "spx-installer"
cat > "${RUN_FILE}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ORIG_DIR="$(pwd)"
ARCHIVE_LINE=$(awk '/^__SPX_PAYLOAD_BELOW__/ {print NR + 1; exit}' "$0")
TMP_DIR=$(mktemp -d)
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

tail -n +"$ARCHIVE_LINE" "$0" | tar -xz -C "$TMP_DIR"
cd "$TMP_DIR/spx-installer"
./spx-install.sh "$@"
STATUS=$?
if [ -d "$TMP_DIR/spx-installer/build" ]; then
  mkdir -p "$ORIG_DIR/build"
  cp -R "$TMP_DIR/spx-installer/build/." "$ORIG_DIR/build/"
  echo "[spx-installer] Copied bundle to $ORIG_DIR/build"
fi
exit $STATUS
__SPX_PAYLOAD_BELOW__
EOF
cat "${tmp_tar}" >> "${RUN_FILE}"
rm -f "${tmp_tar}"
chmod +x "${RUN_FILE}"
echo "[self-extract] Created ${RUN_FILE}"

cat > "${PS1_FILE}" <<'EOF'
#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$payload = @'
EOF

python - "$BASE_DIR" <<'PY' >> "${PS1_FILE}"
import os
import sys
import base64
import io
import zipfile

base_dir = os.path.abspath(sys.argv[1])
prefix = os.path.basename(base_dir.rstrip(os.sep)) or "spx-installer"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(base_dir):
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, base_dir)
            arcname = os.path.join(prefix, rel)
            zf.write(path, arcname)
encoded = base64.b64encode(buf.getvalue()).decode("ascii")
for i in range(0, len(encoded), 76):
    print(encoded[i:i+76])
PY

cat >> "${PS1_FILE}" <<'EOF'
'@

$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("spx-installer-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$zipPath = Join-Path $tmpDir "payload.zip"
$payloadBytes = [Convert]::FromBase64String(($payload -split '\s+') -join "")
[IO.File]::WriteAllBytes($zipPath, $payloadBytes)
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $tmpDir)
Remove-Item $zipPath -Force
$installerPath = Join-Path $tmpDir "spx-installer"
$origDir = Get-Location
$status = 1
try {
    if (Get-Command pwsh -ErrorAction SilentlyContinue) {
        & pwsh -ExecutionPolicy Bypass -File (Join-Path $installerPath "spx-install.ps1") @args
    } elseif (Get-Command powershell -ErrorAction SilentlyContinue) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $installerPath "spx-install.ps1") @args
    } else {
        throw "Neither pwsh nor powershell is available on this system."
    }
    $status = $LASTEXITCODE
    $buildPath = Join-Path $installerPath "build"
    if (Test-Path $buildPath) {
        $dest = Join-Path $origDir "build"
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        Copy-Item -Path (Join-Path $buildPath '*') -Destination $dest -Recurse -Force
        Write-Host "[spx-installer] Copied bundle to $dest"
    }
}
finally {
    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}
exit $status
EOF

chmod +x "${PS1_FILE}"
echo "[self-extract] Created ${PS1_FILE}"
