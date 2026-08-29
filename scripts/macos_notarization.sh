#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

notarize_package() {
  local package_path="$1"
  local staging_root="$2"
  local notary_profile="$3"
  local keychain_path="${4:-}"
  local notary_output_path="${staging_root}/notarytool-submit.log"
  local notarytool_exit=0
  local notary_status=""
  local submission_id=""

  local notarytool_args=(
    notarytool
    submit
    "${package_path}"
    --keychain-profile "${notary_profile}"
    --wait
  )

  if [[ -n "${keychain_path}" ]]; then
    notarytool_args+=(--keychain "${keychain_path}")
  fi

  rm -f "${notary_output_path}"
  echo ""
  echo "Submitting package for notarization..."
  set +e
  xcrun "${notarytool_args[@]}" 2>&1 | tee "${notary_output_path}"
  notarytool_exit="${PIPESTATUS[0]}"
  set -e

  notary_status="$(sed -n 's/^[[:space:]]*status:[[:space:]]*//p' "${notary_output_path}" | tail -n 1 | tr -d '\r')"
  submission_id="$(sed -n 's/^[[:space:]]*id:[[:space:]]*//p' "${notary_output_path}" | head -n 1 | tr -d '\r')"

  if [[ "${notarytool_exit}" -ne 0 || "${notary_status}" != "Accepted" ]]; then
    echo "Notarization did not succeed (status: ${notary_status:-unknown})." >&2
    if [[ -n "${submission_id}" ]]; then
      local notary_log_args=(
        notarytool
        log
        "${submission_id}"
        --keychain-profile "${notary_profile}"
        --output-format json
      )
      if [[ -n "${keychain_path}" ]]; then
        notary_log_args+=(--keychain "${keychain_path}")
      fi
      echo "Apple notarization report:" >&2
      if ! xcrun "${notary_log_args[@]}" >&2; then
        echo "Unable to retrieve the Apple notarization report." >&2
      fi
    else
      echo "Apple did not return a notarization submission ID." >&2
    fi
    return 1
  fi

  rm -f "${notary_output_path}"
  echo ""
  echo "Stapling notarization ticket..."
  xcrun stapler staple "${package_path}"

  echo ""
  echo "Validating stapled ticket..."
  xcrun stapler validate -v "${package_path}"

  echo ""
  echo "Gatekeeper assessment:"
  spctl -a -vv -t install "${package_path}"
}
