#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_installer_package.sh [--output-dir DIR] [--package-name NAME]

Creates a portable installer archive (tgz) with the wizard CLI, manifests,
and helper scripts so end users can run `spx-setup` without cloning the repo.

Options:
  --output-dir DIR     Directory to place the assembled folder and tarball (default: dist)
  --package-name NAME  Name of the folder/tarball (default: spx-installer)
EOF
}

OUTPUT_DIR="dist"
PACKAGE_NAME="spx-installer"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --package-name)
      PACKAGE_NAME="$2"
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

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
PACKAGE_DIR="${DEST_DIR}/${PACKAGE_NAME}"
ARCHIVE_PATH="${DEST_DIR}/${PACKAGE_NAME}.tgz"

mkdir -p "${DEST_DIR}"
rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"

copy_entries=(
  "installer"
  "library"
  "profiles"
  "extensions"
  "spx_mcp"
  "tools"
  "docs"
  "AGENTS.md"
  "LICENSE"
  "THIRD_PARTY_NOTICE.txt"
  "spx-setup.command"
  "spx-setup.desktop"
  "spx-setup.sh"
  "spx-setup.bat"
  "spx-mcp-setup.command"
  "spx-mcp-setup.sh"
  "spx-install.sh"
  "spx-install.ps1"
  "README.md"
  "pyproject.toml"
  "poetry.lock"
)

rsync_opts=(
  "-a"
  "--delete-excluded"
  "--exclude" "__pycache__"
  "--exclude" ".pytest_cache"
  "--exclude" ".mypy_cache"
)

command -v rsync >/dev/null 2>&1 || { echo "rsync is required for packaging." >&2; exit 1; }

for entry in "${copy_entries[@]}"; do
  src="${REPO_ROOT}/${entry}"
  if [[ ! -e "${src}" ]]; then
    echo "Skipping missing entry: ${entry}"
    continue
  fi
  rsync "${rsync_opts[@]}" "${src}" "${PACKAGE_DIR}/"
done

normalize_text_line_endings() {
  local package_dir="$1"
  python3 - "$package_dir" <<'PY'
from __future__ import annotations

import pathlib
import sys

root = pathlib.Path(sys.argv[1])
extensions = {".sh", ".desktop", ".command", ".ps1", ".md", ".toml", ".yaml", ".yml", ".py"}
for path in root.rglob("*"):
    if not path.is_file():
        continue
    if path.suffix.lower() not in extensions:
        continue
    text = path.read_text(encoding="utf-8", errors="surrogatepass")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized != text:
        path.write_text(normalized, encoding="utf-8", newline="\n")
PY
}

normalize_text_line_endings "${PACKAGE_DIR}"

cat > "${PACKAGE_DIR}/INSTALLER_README.md" <<'EOF'
# SPX Installer Package

This archive contains the interactive installer (launch via `spx-setup.*`),
the manifest library, and all helper scripts required to generate a deployment bundle
without cloning the full spx-examples repository.

## Requirements

- Python 3.9+ with `pip`
- Docker Desktop / Docker Engine with Compose V2
- Python 3.10+ if you want to bootstrap the local Codex MCP workspace
- On Ubuntu/Debian, if the runtime venv cannot bootstrap pip, install `python3-venv` and, if needed, `python3-pip`

## Licensing

- Open-source license notices bundled with this package apply to the corresponding components, including the included `LICENSE` file.
- Third-party distribution notes for installer-bundled dependencies are included in `THIRD_PARTY_NOTICE.txt`.
- Proprietary SPX features, branding, hosted services, and subscription-gated functionality may require separate commercial terms or authorization.

## Usage

1. Extract this archive (e.g. `tar -xzf spx-installer.tgz`).
2. Run the installer:
   - macOS: `./spx-setup.command`
   - Linux desktop: `./spx-setup.desktop`
   - Windows: `spx-setup.bat`
   - macOS/Linux shells: `./spx-setup.sh`
3. Follow the wizard prompts. Artifacts are written to `build/spx-generated/` by default.
4. Inside the generated directory run `./spx-start.sh` (or `pwsh ./spx-start.ps1`) to start the stack.

## Optional Codex MCP workspace

If you want a repo-like workspace that Codex can open with the local `spx-mcp`
server preconfigured, run:

- macOS: `./spx-mcp-setup.command`
- macOS/Linux shells: `./spx-mcp-setup.sh`

This creates an installer-managed workspace and a local `.codex/config.toml`
for that folder. Open Codex in the generated workspace and start a fresh thread.

You can safely redistribute the extracted folder (including `build/spx-generated`) to teammates.
EOF

rm -f "${ARCHIVE_PATH}"
tar -czf "${ARCHIVE_PATH}" -C "${DEST_DIR}" "${PACKAGE_NAME}"

echo "Created installer folder: ${PACKAGE_DIR}"
echo "Created archive: ${ARCHIVE_PATH}"
