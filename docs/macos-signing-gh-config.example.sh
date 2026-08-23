#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

# Copy this file outside the repository, fill in the local paths and public
# identity values, then run it with: bash macos-signing-gh-config.sh
#
# The script never stores certificate contents or passwords in the repository.
# It streams the encoded files to `gh secret set` and prompts for the P12
# password without echoing it.

REPO="HammerHeads-Engineers/spx-examples"
ENVIRONMENT="macos-signing"

# Local files exported from Keychain Access, including their private keys.
APP_CERT_P12_PATH="/absolute/path/to/developer-id-application.p12"
INSTALLER_CERT_P12_PATH="/absolute/path/to/developer-id-installer.p12"
NOTARY_KEY_P8_PATH="/absolute/path/to/AuthKey_KEY_ID.p8"

# Public identity and App Store Connect values. They are stored as GitHub
# Environment Variables, not as Secrets.
APP_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID1234)"
INSTALLER_SIGN_IDENTITY="Developer ID Installer: Your Company (TEAMID1234)"
TEAM_ID="TEAMID1234"
NOTARY_KEY_ID="KEY_ID"
NOTARY_ISSUER_ID="ISSUER_ID"
NOTARY_PROFILE="spx-notary"

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "Missing file: ${path}" >&2
    exit 1
  fi
}

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" || "${value}" == *"/absolute/path/"* || "${value}" == *"Your Company"* || "${value}" == "TEAMID1234" || "${value}" == "KEY_ID" || "${value}" == "ISSUER_ID" ]]; then
    echo "Fill in ${name} before running this script." >&2
    exit 1
  fi
}

command -v gh >/dev/null 2>&1 || {
  echo "GitHub CLI (gh) is required." >&2
  exit 1
}

gh auth status >/dev/null
require_file "${APP_CERT_P12_PATH}"
require_file "${INSTALLER_CERT_P12_PATH}"
require_file "${NOTARY_KEY_P8_PATH}"
require_value "APP_SIGN_IDENTITY" "${APP_SIGN_IDENTITY}"
require_value "INSTALLER_SIGN_IDENTITY" "${INSTALLER_SIGN_IDENTITY}"
require_value "TEAM_ID" "${TEAM_ID}"
require_value "NOTARY_KEY_ID" "${NOTARY_KEY_ID}"
require_value "NOTARY_ISSUER_ID" "${NOTARY_ISSUER_ID}"
require_value "NOTARY_PROFILE" "${NOTARY_PROFILE}"

read -r -s -p "Password used for both P12 exports: " CERT_PASSWORD
printf '\n'
if [[ -z "${CERT_PASSWORD}" ]]; then
  echo "The P12 password cannot be empty." >&2
  exit 1
fi

echo "Setting macOS signing variables in ${REPO}/${ENVIRONMENT}..."
gh variable set MACOS_APP_SIGN_IDENTITY \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${APP_SIGN_IDENTITY}"
gh variable set MACOS_INSTALLER_SIGN_IDENTITY \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${INSTALLER_SIGN_IDENTITY}"
gh variable set MACOS_TEAM_ID \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${TEAM_ID}"
gh variable set MACOS_NOTARY_KEY_ID \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${NOTARY_KEY_ID}"
gh variable set MACOS_NOTARY_ISSUER_ID \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${NOTARY_ISSUER_ID}"
gh variable set MACOS_NOTARY_PROFILE \
  --repo "${REPO}" --env "${ENVIRONMENT}" --body "${NOTARY_PROFILE}"

echo "Setting macOS signing secrets..."
base64 -i "${APP_CERT_P12_PATH}" | tr -d '\n' | \
  gh secret set MACOS_APP_CERT_P12_BASE64 \
    --repo "${REPO}" --env "${ENVIRONMENT}"
base64 -i "${INSTALLER_CERT_P12_PATH}" | tr -d '\n' | \
  gh secret set MACOS_INSTALLER_CERT_P12_BASE64 \
    --repo "${REPO}" --env "${ENVIRONMENT}"
printf '%s' "${CERT_PASSWORD}" | \
  gh secret set MACOS_CERT_PASSWORD \
    --repo "${REPO}" --env "${ENVIRONMENT}"
base64 -i "${NOTARY_KEY_P8_PATH}" | tr -d '\n' | \
  gh secret set MACOS_NOTARY_KEY_BASE64 \
    --repo "${REPO}" --env "${ENVIRONMENT}"
unset CERT_PASSWORD

echo "Configured GitHub Environment variables:"
gh variable list --repo "${REPO}" --env "${ENVIRONMENT}"
echo "Configured GitHub Environment secrets (values are not displayed):"
gh secret list --repo "${REPO}" --env "${ENVIRONMENT}"

cat <<EOF

Values are configured. The workflow job must reference:

  environment: ${ENVIRONMENT}

and import the P12 files plus the .p8 key before calling
scripts/build_macos_pkg.sh with --app-sign, --sign, --keychain, and
--notarytool-profile ${NOTARY_PROFILE}.
EOF
