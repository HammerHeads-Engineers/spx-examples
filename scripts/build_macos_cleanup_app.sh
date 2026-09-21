#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_macos_cleanup_app.sh [options]

Builds SPX Cleanup.app, a small macOS launcher that opens Terminal and removes
the local SPX generated environment plus related Docker resources.

Options:
  --output-dir DIR    Directory where the app bundle will be created (default: dist)
  --app-name NAME     App bundle name without extension (default: SPX Cleanup)
  --bundle-id ID      CFBundleIdentifier for the app (default: com.hammerheadsengineers.spx.cleanup)
  --version VERSION   App version (default: pyproject.toml version or dev)
  --sign IDENTITY     Sign with this Developer ID Application identity
  -h, --help          Show this help
EOF
}

OUTPUT_DIR="dist"
APP_NAME="SPX Cleanup"
BUNDLE_ID="com.hammerheadsengineers.spx.cleanup"
VERSION=""
SIGN_IDENTITY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    --bundle-id)
      BUNDLE_ID="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    --sign)
      SIGN_IDENTITY="$2"
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

build_args=(
  --output-dir "${OUTPUT_DIR}"
  --app-name "${APP_NAME}"
  --bundle-id "${BUNDLE_ID}"
  --script-source "installer/macos/spx_cleanup_launcher.applescript"
  --skip-payload
)

if [[ -n "${VERSION}" ]]; then
  build_args+=(--version "${VERSION}")
fi

if [[ -n "${SIGN_IDENTITY}" ]]; then
  build_args+=(--sign "${SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_setup_app.sh" "${build_args[@]}"
