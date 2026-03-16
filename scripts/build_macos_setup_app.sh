#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_macos_setup_app.sh [options]

Builds a macOS launcher app bundle that embeds the full SPX installer payload.
The resulting app can be installed into /Applications and launched from Finder;
it opens Terminal and starts the existing terminal-based installer flow from the
bundle's Resources directory.

Options:
  --output-dir DIR    Directory where the app bundle will be created (default: dist)
  --staging-dir DIR   Directory for intermediate payload files (default: build/macos-app)
  --app-name NAME     App bundle name without extension (default: SPX Setup)
  --bundle-id ID      CFBundleIdentifier for the app (default: com.hammerheadsengineers.spx.setup)
  --version VERSION   App version (default: pyproject.toml version or dev)
  --sign IDENTITY     Sign with this Developer ID Application identity
  -h, --help          Show this help
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

resolve_version() {
  local version
  version="$(sed -n 's/^version = "\(.*\)"$/\1/p' "${REPO_ROOT}/pyproject.toml" | head -n 1)"
  if [[ -n "${version}" ]]; then
    printf '%s\n' "${version}"
    return
  fi
  printf 'dev\n'
}

OUTPUT_DIR="dist"
STAGING_DIR="build/macos-app"
APP_NAME="SPX Setup"
BUNDLE_ID="com.hammerheadsengineers.spx.setup"
VERSION=""
SIGN_IDENTITY=""
PAYLOAD_NAME="spx-installer"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --staging-dir)
      STAGING_DIR="$2"
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

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "scripts/build_macos_setup_app.sh must be run on macOS." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
STAGING_ROOT="${REPO_ROOT}/${STAGING_DIR}"
PAYLOAD_DIR="${STAGING_ROOT}/${PAYLOAD_NAME}"
SCRIPT_SOURCE="${REPO_ROOT}/installer/macos/spx_setup_launcher.applescript"
APP_PATH="${DEST_DIR}/${APP_NAME}.app"

if [[ -z "${VERSION}" ]]; then
  VERSION="$(resolve_version)"
fi

require_command xcrun
require_command rsync
require_command sed
require_command /usr/libexec/PlistBuddy
require_command codesign

mkdir -p "${DEST_DIR}"
mkdir -p "${STAGING_ROOT}"
rm -rf "${APP_PATH}"

"${REPO_ROOT}/scripts/build_installer_package.sh" \
  --output-dir "${STAGING_DIR}" \
  --package-name "${PAYLOAD_NAME}"

xcrun osacompile -o "${APP_PATH}" "${SCRIPT_SOURCE}"

RESOURCE_PAYLOAD_DIR="${APP_PATH}/Contents/Resources/${PAYLOAD_NAME}"
mkdir -p "${RESOURCE_PAYLOAD_DIR}"
rsync -a --delete "${PAYLOAD_DIR}/" "${RESOURCE_PAYLOAD_DIR}/"

plist="${APP_PATH}/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string '${BUNDLE_ID}'" "${plist}" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier '${BUNDLE_ID}'" "${plist}"
/usr/libexec/PlistBuddy -c "Set :CFBundleName '${APP_NAME}'" "${plist}"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string '${APP_NAME}'" "${plist}" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName '${APP_NAME}'" "${plist}"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string '${VERSION}'" "${plist}" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString '${VERSION}'" "${plist}"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string '${VERSION}'" "${plist}" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion '${VERSION}'" "${plist}"
/usr/libexec/PlistBuddy -c "Add :LSApplicationCategoryType string 'public.app-category.developer-tools'" "${plist}" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :LSApplicationCategoryType 'public.app-category.developer-tools'" "${plist}"

privacy_keys=(
  NSAppleEventsUsageDescription
  NSAppleMusicUsageDescription
  NSCalendarsUsageDescription
  NSCameraUsageDescription
  NSContactsUsageDescription
  NSHomeKitUsageDescription
  NSMicrophoneUsageDescription
  NSPhotoLibraryUsageDescription
  NSRemindersUsageDescription
  NSSiriUsageDescription
  NSSystemAdministrationUsageDescription
)

for key in "${privacy_keys[@]}"; do
  /usr/libexec/PlistBuddy -c "Delete :${key}" "${plist}" >/dev/null 2>&1 || true
done

if [[ -n "${SIGN_IDENTITY}" ]]; then
  if [[ "${SIGN_IDENTITY}" != Developer\ ID\ Application:* ]]; then
    echo "Warning: app signing normally uses a 'Developer ID Application' identity." >&2
  fi

  codesign --force --sign "${SIGN_IDENTITY}" --timestamp --options runtime "${APP_PATH}"

  echo ""
  echo "App signature:"
  codesign --verify --verbose=2 "${APP_PATH}"
  echo ""
  echo "Gatekeeper assessment:"
  spctl -a -vv "${APP_PATH}" || true
else
  codesign --force --sign - "${APP_PATH}"

  echo ""
  echo "App bundle refreshed with an ad-hoc signature for local use."
  echo "Sign it with --sign \"Developer ID Application: Your Company (TEAMID1234)\" for notarized distribution."
fi

echo "Created macOS launcher app: ${APP_PATH}"
