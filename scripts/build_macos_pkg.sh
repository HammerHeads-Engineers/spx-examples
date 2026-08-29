#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_macos_pkg.sh [options]

 Builds a macOS flat installer package (.pkg) that installs SPX Setup.app,
 SPX MCP Setup.app, SPX Start.app, SPX Stop.app, SPX Cleanup.app, and
 SPX Uninstall.app into /Applications/SPX Tools. SPX Setup.app contains the
 full installer payload; the other launchers operate on the generated
 environment in the user's Application Support directory, bootstrap a managed
 SPX MCP workspace, or remove the installed SPX tools.

Options:
  --output-dir DIR              Directory for the final .pkg (default: dist)
  --staging-dir DIR             Directory for intermediate app/pkg files (default: build/macos-pkg)
  --pkg-name NAME               Output package stem without version/ext (default: spx-installer-macos)
  --identifier ID               macOS package identifier (default: com.hammerheadsengineers.spx.installer)
  --version VERSION             Package version (default: pyproject.toml version or dev)
  --install-location PATH       Parent install destination on macOS (default: /Applications)
  --app-name NAME               Installed launcher app name without extension (default: SPX Setup)
  --app-bundle-id ID            CFBundleIdentifier for the launcher app (default: com.hammerheadsengineers.spx.setup)
  --app-sign IDENTITY           Sign the launcher app with this Developer ID Application identity
  --sign IDENTITY               Sign the .pkg with this Developer ID Installer identity
  --keychain PATH               Optional keychain for pkg signing / notarytool profile lookup
  --notarytool-profile PROFILE  Submit the signed .pkg with this notarytool keychain profile
  --python-version VERSION      Official universal2 Python version to bundle (default: 3.12.10)
  --python-package PATH         Use a local official Python macOS .pkg instead of downloading it
  --python-sha256 SHA256        Expected SHA-256 for the Python package
  -h, --help                    Show this help
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

apply_folder_icon() {
  local folder_path="$1"
  local icon_source="$2"
  local icon_path="${folder_path}/Icon"$'\r'

  cp "${icon_source}" "${icon_path}"
  chflags hidden "${icon_path}"
  xattr -wx com.apple.FinderInfo \
    0000000000000000040000000000000000000000000000000000000000000000 \
    "${folder_path}"
  xattr -wx com.apple.FinderInfo \
    0000000000000000400000000000000000000000000000000000000000000000 \
    "${icon_path}"
}

write_pkg_scripts() {
  local scripts_dir="$1"
  local install_root="$2"
  local tools_dir_name="$3"

  mkdir -p "${scripts_dir}"

  cat > "${scripts_dir}/postinstall" <<EOF
#!/bin/bash
set -euo pipefail

tools_dir="${install_root}/${tools_dir_name}"
setup_icon="\${tools_dir}/SPX Setup.app/Contents/Resources/spx.icns"
folder_icon="\${tools_dir}/Icon"$'\r'

if [[ -d "\${tools_dir}" && -f "\${setup_icon}" ]]; then
  cp "\${setup_icon}" "\${folder_icon}"
  chflags hidden "\${folder_icon}" || true
  xattr -wx com.apple.FinderInfo \
    0000000000000000040000000000000000000000000000000000000000000000 \
    "\${tools_dir}" || true
  xattr -wx com.apple.FinderInfo \
    0000000000000000400000000000000000000000000000000000000000000000 \
    "\${folder_icon}" || true
fi
EOF

  chmod +x "${scripts_dir}/postinstall"
}

write_distribution_file() {
  local distribution_path="$1"
  local package_id="$2"
  local package_file_name="$3"
  local python_package_id="$4"
  local python_package_file_name="$5"
  local python_version="$6"
  local version="$7"
  local title="$8"

  cat > "${distribution_path}" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>${title}</title>
    <license file="License.rtf"/>
    <pkg-ref id="${package_id}"/>
    <pkg-ref id="${python_package_id}"/>
    <options customize="never" require-scripts="false" hostArchitectures="x86_64,arm64"/>
    <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
    <choices-outline>
        <line choice="default">
            <line choice="${package_id}"/>
            <line choice="${python_package_id}"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="${package_id}" visible="false">
        <pkg-ref id="${package_id}"/>
    </choice>
    <pkg-ref id="${package_id}" version="${version}" onConclusion="none">${package_file_name}</pkg-ref>
    <choice id="${python_package_id}" visible="false">
        <pkg-ref id="${python_package_id}"/>
    </choice>
    <pkg-ref id="${python_package_id}" version="${python_version}" onConclusion="none">${python_package_file_name}</pkg-ref>
</installer-gui-script>
EOF
}

prepare_python_component() {
  local package_path="${STAGING_ROOT}/python-${PYTHON_VERSION}.pkg"
  local expanded_path="${STAGING_ROOT}/python-expanded"
  local framework_payload="${expanded_path}/Python_Framework.pkg/Payload"

  if [[ -n "${PYTHON_PACKAGE_INPUT}" ]]; then
    if [[ ! -f "${PYTHON_PACKAGE_INPUT}" ]]; then
      echo "Python package not found: ${PYTHON_PACKAGE_INPUT}" >&2
      exit 1
    fi
    cp "${PYTHON_PACKAGE_INPUT}" "${package_path}"
  else
    require_command curl
    echo "Downloading universal2 Python ${PYTHON_VERSION} package..."
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 \
      "${PYTHON_PACKAGE_URL}" \
      --output "${package_path}"
  fi

  local actual_sha256
  actual_sha256="$(shasum -a 256 "${package_path}" | awk '{print $1}')"
  if [[ "${actual_sha256}" != "${PYTHON_PACKAGE_SHA256}" ]]; then
    echo "Python package checksum mismatch." >&2
    echo "  Expected: ${PYTHON_PACKAGE_SHA256}" >&2
    echo "  Actual:   ${actual_sha256}" >&2
    exit 1
  fi

  rm -rf "${expanded_path}" "${PYTHON_FRAMEWORK_ROOT}"
  pkgutil --expand-full "${package_path}" "${expanded_path}"
  if [[ ! -d "${framework_payload}" ]]; then
    echo "Official Python package does not contain Python_Framework.pkg/Payload." >&2
    exit 1
  fi

  mkdir -p "${PYTHON_FRAMEWORK_ROOT}"
  rsync -a --delete --exclude '._*' "${framework_payload}/" "${PYTHON_FRAMEWORK_ROOT}/"

  local python_bin="${PYTHON_FRAMEWORK_ROOT}/Versions/${PYTHON_FRAMEWORK_VERSION}/bin/python${PYTHON_FRAMEWORK_VERSION}"
  if [[ ! -x "${python_bin}" ]]; then
    echo "Bundled Python executable is missing: ${python_bin}" >&2
    exit 1
  fi
  if ! file "${python_bin}" | grep -q "universal binary"; then
    echo "Bundled Python executable is not universal2: ${python_bin}" >&2
    exit 1
  fi
  codesign --verify --deep --strict \
    "${PYTHON_FRAMEWORK_ROOT}/Versions/${PYTHON_FRAMEWORK_VERSION}/Resources/Python.app"

  local python_scripts_dir="${STAGING_ROOT}/python-scripts"
  rm -rf "${python_scripts_dir}"
  mkdir -p "${python_scripts_dir}"
  cat > "${python_scripts_dir}/postinstall" <<EOF
#!/bin/sh
set -eu

framework_root="/Library/Frameworks/Python.framework/Versions/${PYTHON_FRAMEWORK_VERSION}"
python_bin="\${framework_root}/bin/python${PYTHON_FRAMEWORK_VERSION}"
compileall="\${framework_root}/lib/python${PYTHON_FRAMEWORK_VERSION}/compileall.py"

if [ -x "\${python_bin}" ] && [ -f "\${compileall}" ]; then
  "\${python_bin}" -E -s -Wi "\${compileall}" -q -j0 \\
    -f -x 'bad_coding|badsyntax|site-packages|test/test_lib2to3/data' \\
    "\${framework_root}/lib/python${PYTHON_FRAMEWORK_VERSION}"
fi
EOF
  chmod +x "${python_scripts_dir}/postinstall"

  python_pkgbuild_args=(
    --root "${PYTHON_FRAMEWORK_ROOT}"
    --scripts "${python_scripts_dir}"
    --identifier "${PYTHON_COMPONENT_ID}"
    --version "${PYTHON_VERSION}"
    --install-location "/Library/Frameworks/Python.framework"
    --ownership recommended
  )

  if [[ -n "${SIGN_IDENTITY}" ]]; then
    python_pkgbuild_args+=(--sign "${SIGN_IDENTITY}")
    if [[ -n "${KEYCHAIN_PATH}" ]]; then
      python_pkgbuild_args+=(--keychain "${KEYCHAIN_PATH}")
    fi
  fi

  pkgbuild "${python_pkgbuild_args[@]}" "${PYTHON_COMPONENT_PKG_PATH}"
}

OUTPUT_DIR="dist"
STAGING_DIR="build/macos-pkg"
PKG_NAME="spx-installer-macos"
IDENTIFIER="com.hammerheadsengineers.spx.installer"
VERSION=""
INSTALL_LOCATION="/Applications"
APP_NAME="SPX Setup"
APP_BUNDLE_ID="com.hammerheadsengineers.spx.setup"
MCP_SETUP_APP_NAME="SPX MCP Setup"
MCP_SETUP_APP_BUNDLE_ID="com.hammerheadsengineers.spx.mcp.setup"
START_APP_NAME="SPX Start"
START_APP_BUNDLE_ID="com.hammerheadsengineers.spx.start"
STOP_APP_NAME="SPX Stop"
STOP_APP_BUNDLE_ID="com.hammerheadsengineers.spx.stop"
CLEANUP_APP_NAME="SPX Cleanup"
CLEANUP_APP_BUNDLE_ID="com.hammerheadsengineers.spx.cleanup"
UNINSTALL_APP_NAME="SPX Uninstall"
UNINSTALL_APP_BUNDLE_ID="com.hammerheadsengineers.spx.uninstall"
TOOLS_DIR_NAME="SPX Tools"
APP_SIGN_IDENTITY=""
SIGN_IDENTITY=""
KEYCHAIN_PATH=""
NOTARYTOOL_PROFILE=""
PYTHON_VERSION="3.12.10"
PYTHON_PACKAGE_INPUT=""
PYTHON_PACKAGE_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
PRODUCT_TITLE="SPX Tools"

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
    --pkg-name)
      PKG_NAME="$2"
      shift 2
      ;;
    --identifier)
      IDENTIFIER="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    --install-location)
      INSTALL_LOCATION="$2"
      shift 2
      ;;
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    --app-bundle-id)
      APP_BUNDLE_ID="$2"
      shift 2
      ;;
    --app-sign)
      APP_SIGN_IDENTITY="$2"
      shift 2
      ;;
    --sign)
      SIGN_IDENTITY="$2"
      shift 2
      ;;
    --keychain)
      KEYCHAIN_PATH="$2"
      shift 2
      ;;
    --notarytool-profile)
      NOTARYTOOL_PROFILE="$2"
      shift 2
      ;;
    --python-version)
      PYTHON_VERSION="$2"
      shift 2
      ;;
    --python-package)
      PYTHON_PACKAGE_INPUT="$2"
      shift 2
      ;;
    --python-sha256)
      PYTHON_PACKAGE_SHA256="$2"
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
  echo "scripts/build_macos_pkg.sh must be run on macOS." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${OUTPUT_DIR}" = /* ]]; then
  DEST_DIR="${OUTPUT_DIR}"
else
  DEST_DIR="${REPO_ROOT}/${OUTPUT_DIR}"
fi
STAGING_ROOT="${REPO_ROOT}/${STAGING_DIR}"
APP_ROOT="${STAGING_ROOT}/root"
PYTHON_FRAMEWORK_VERSION="${PYTHON_VERSION%.*}"
PYTHON_PACKAGE_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-macos11.pkg"
PYTHON_COMPONENT_ID="com.hammerheadsengineers.spx.python"
APP_OUTPUT_DIR="${STAGING_DIR}/root/${TOOLS_DIR_NAME}"
APP_INSTALL_ROOT="${APP_ROOT}/${TOOLS_DIR_NAME}"
PYTHON_FRAMEWORK_ROOT="${STAGING_ROOT}/python-framework-root"
PKG_SCRIPTS_DIR="${STAGING_ROOT}/pkg-scripts"
MACOS_RESOURCES_DIR="${REPO_ROOT}/packaging/macos/resources"

if [[ -z "${VERSION}" ]]; then
  VERSION="$(resolve_version)"
fi
if [[ ! "${PYTHON_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Python version must use the X.Y.Z format: ${PYTHON_VERSION}" >&2
  exit 1
fi
if [[ ! "${PYTHON_PACKAGE_SHA256}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "Python package SHA-256 must contain exactly 64 hexadecimal characters." >&2
  exit 1
fi
PYTHON_COMPONENT_PKG_PATH="${STAGING_ROOT}/${PKG_NAME}-${VERSION}-python-component.pkg"

if [[ -n "${NOTARYTOOL_PROFILE}" && -z "${SIGN_IDENTITY}" ]]; then
  echo "--notarytool-profile requires --sign with a Developer ID Installer identity." >&2
  exit 1
fi

if [[ -n "${NOTARYTOOL_PROFILE}" && -z "${APP_SIGN_IDENTITY}" ]]; then
  echo "--notarytool-profile requires --app-sign with a Developer ID Application identity." >&2
  exit 1
fi

if [[ -n "${SIGN_IDENTITY}" && "${SIGN_IDENTITY}" != Developer\ ID\ Installer:* ]]; then
  echo "Warning: pkg signing normally uses a 'Developer ID Installer' identity." >&2
fi

require_command pkgbuild
require_command productbuild
require_command pkgutil
require_command rsync
require_command shasum
require_command file
require_command codesign
require_command sed
require_command /usr/libexec/PlistBuddy
require_command chflags
require_command xattr

if [[ ! -d "${MACOS_RESOURCES_DIR}" ]]; then
  echo "Missing macOS installer resources directory: ${MACOS_RESOURCES_DIR}" >&2
  exit 1
fi

mkdir -p "${DEST_DIR}"
rm -rf "${APP_ROOT}"
rm -rf "${PYTHON_FRAMEWORK_ROOT}"
rm -rf "${STAGING_ROOT}/python-scripts"
rm -rf "${PKG_SCRIPTS_DIR}"
mkdir -p "${APP_INSTALL_ROOT}"

build_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --staging-dir "${STAGING_DIR}/payload"
  --app-name "${APP_NAME}"
  --bundle-id "${APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_setup_app.sh" "${build_app_args[@]}"

build_mcp_setup_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --app-name "${MCP_SETUP_APP_NAME}"
  --bundle-id "${MCP_SETUP_APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_mcp_setup_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_mcp_setup_app.sh" "${build_mcp_setup_app_args[@]}"

build_start_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --app-name "${START_APP_NAME}"
  --bundle-id "${START_APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_start_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_start_app.sh" "${build_start_app_args[@]}"

build_stop_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --app-name "${STOP_APP_NAME}"
  --bundle-id "${STOP_APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_stop_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_stop_app.sh" "${build_stop_app_args[@]}"

build_cleanup_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --app-name "${CLEANUP_APP_NAME}"
  --bundle-id "${CLEANUP_APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_cleanup_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_cleanup_app.sh" "${build_cleanup_app_args[@]}"

build_uninstall_app_args=(
  --output-dir "${APP_OUTPUT_DIR}"
  --app-name "${UNINSTALL_APP_NAME}"
  --bundle-id "${UNINSTALL_APP_BUNDLE_ID}"
  --version "${VERSION}"
)

if [[ -n "${APP_SIGN_IDENTITY}" ]]; then
  build_uninstall_app_args+=(--sign "${APP_SIGN_IDENTITY}")
fi

"${REPO_ROOT}/scripts/build_macos_uninstall_app.sh" "${build_uninstall_app_args[@]}"

apply_folder_icon \
  "${APP_INSTALL_ROOT}" \
  "${APP_INSTALL_ROOT}/${APP_NAME}.app/Contents/Resources/spx.icns"
write_pkg_scripts "${PKG_SCRIPTS_DIR}" "${INSTALL_LOCATION}" "${TOOLS_DIR_NAME}"

PKG_PATH="${DEST_DIR}/${PKG_NAME}-${VERSION}.pkg"
COMPONENT_PLIST="${STAGING_ROOT}/component.plist"
COMPONENT_PKG_PATH="${STAGING_ROOT}/${PKG_NAME}-${VERSION}-component.pkg"
DISTRIBUTION_PATH="${STAGING_ROOT}/Distribution.xml"
rm -f "${PKG_PATH}"
rm -f "${COMPONENT_PLIST}"
rm -f "${COMPONENT_PKG_PATH}"
rm -f "${PYTHON_COMPONENT_PKG_PATH}"
rm -f "${DISTRIBUTION_PATH}"

pkgbuild --analyze --root "${APP_ROOT}" "${COMPONENT_PLIST}"

component_index=0
while /usr/libexec/PlistBuddy -c "Print :${component_index}" "${COMPONENT_PLIST}" >/dev/null 2>&1; do
  /usr/libexec/PlistBuddy -c "Set :${component_index}:BundleIsRelocatable false" "${COMPONENT_PLIST}" >/dev/null 2>&1 || true
  component_index=$((component_index + 1))
done

pkgbuild_args=(
  --root "${APP_ROOT}"
  --scripts "${PKG_SCRIPTS_DIR}"
  --component-plist "${COMPONENT_PLIST}"
  --identifier "${IDENTIFIER}"
  --version "${VERSION}"
  --install-location "${INSTALL_LOCATION}"
  --ownership recommended
)

if [[ -n "${SIGN_IDENTITY}" ]]; then
  pkgbuild_args+=(--sign "${SIGN_IDENTITY}")
  if [[ -n "${KEYCHAIN_PATH}" ]]; then
    pkgbuild_args+=(--keychain "${KEYCHAIN_PATH}")
  fi
fi

pkgbuild "${pkgbuild_args[@]}" "${COMPONENT_PKG_PATH}"

prepare_python_component

write_distribution_file \
  "${DISTRIBUTION_PATH}" \
  "${IDENTIFIER}" \
  "$(basename "${COMPONENT_PKG_PATH}")" \
  "${PYTHON_COMPONENT_ID}" \
  "$(basename "${PYTHON_COMPONENT_PKG_PATH}")" \
  "${PYTHON_VERSION}" \
  "${VERSION}" \
  "${PRODUCT_TITLE}"

productbuild_args=(
  --distribution "${DISTRIBUTION_PATH}"
  --resources "${MACOS_RESOURCES_DIR}"
  --package-path "${STAGING_ROOT}"
  --version "${VERSION}"
)

if [[ -n "${SIGN_IDENTITY}" ]]; then
  productbuild_args+=(--sign "${SIGN_IDENTITY}")
  if [[ -n "${KEYCHAIN_PATH}" ]]; then
    productbuild_args+=(--keychain "${KEYCHAIN_PATH}")
  fi
fi

productbuild "${productbuild_args[@]}" "${PKG_PATH}"

echo "Created macOS package: ${PKG_PATH}"
echo "Bundled universal2 Python runtime: ${PYTHON_VERSION}"

if [[ -n "${SIGN_IDENTITY}" ]]; then
  echo ""
  echo "Package signature:"
  pkgutil --check-signature "${PKG_PATH}"
fi

if [[ -n "${NOTARYTOOL_PROFILE}" ]]; then
  require_command xcrun

  notarytool_args=(
    notarytool
    submit
    "${PKG_PATH}"
    --keychain-profile "${NOTARYTOOL_PROFILE}"
    --wait
  )

  if [[ -n "${KEYCHAIN_PATH}" ]]; then
    notarytool_args+=(--keychain "${KEYCHAIN_PATH}")
  fi

  echo ""
  echo "Submitting package for notarization..."
  xcrun "${notarytool_args[@]}"

  echo ""
  echo "Stapling notarization ticket..."
  xcrun stapler staple "${PKG_PATH}"

  echo ""
  echo "Validating stapled ticket..."
  xcrun stapler validate -v "${PKG_PATH}"

  echo ""
  echo "Gatekeeper assessment:"
  spctl -a -vv -t install "${PKG_PATH}"
elif [[ -z "${SIGN_IDENTITY}" ]]; then
  echo ""
  echo "Package is unsigned. Gatekeeper will reject it until you rebuild with:"
  echo "  --app-sign \"Developer ID Application: Your Company (TEAMID1234)\""
  echo "  --sign \"Developer ID Installer: Your Company (TEAMID1234)\""
else
  echo ""
  if [[ -z "${APP_SIGN_IDENTITY}" ]]; then
    echo "Launcher app is unsigned. Rebuild with --app-sign before notarized distribution."
  fi
  echo "Package is signed but not notarized."
  echo "Re-run with --notarytool-profile PROFILE to submit and staple the package."
fi
