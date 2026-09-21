#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: sync_release_to_www.sh --repository OWNER/REPOSITORY --tag TAG

Environment:
  SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED
  SPX_WWW_DOWNLOAD_SYNC_ENABLED
  SPX_WWW_STAGING_DOWNLOAD_SYNC_URL
  SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN
  SPX_WWW_DOWNLOAD_SYNC_URL
  SPX_WWW_DOWNLOAD_SYNC_TOKEN
EOF
}

repository=""
tag=""

while (($# > 0)); do
  case "$1" in
    --repository)
      if (($# < 2)); then
        usage
        exit 2
      fi
      repository="$2"
      shift 2
      ;;
    --tag)
      if (($# < 2)); then
        usage
        exit 2
      fi
      tag="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${repository}" || -z "${tag}" ]]; then
  echo "Both --repository and --tag are required." >&2
  usage
  exit 2
fi

staging_enabled="${SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED:-false}"
production_enabled="${SPX_WWW_DOWNLOAD_SYNC_ENABLED:-false}"

if [[ "${staging_enabled}" != "true" && "${production_enabled}" != "true" ]]; then
  echo "SPX WWW Downloads sync is disabled; enable staging or production after the endpoints are ready."
  exit 0
fi

require_configuration() {
  local variable_name="$1"
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Missing required SPX WWW sync configuration: ${variable_name}" >&2
    exit 1
  fi
}

if [[ "${staging_enabled}" == "true" ]]; then
  require_configuration SPX_WWW_STAGING_DOWNLOAD_SYNC_URL
  require_configuration SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN
fi

if [[ "${production_enabled}" == "true" ]]; then
  require_configuration SPX_WWW_DOWNLOAD_SYNC_URL
  require_configuration SPX_WWW_DOWNLOAD_SYNC_TOKEN
fi

payload="$(jq -cn \
  --arg event "release_assets_ready" \
  --arg repository "${repository}" \
  --arg tag "${tag}" \
  '{event: $event, repository: $repository, tag: $tag, assets_ready: true}')"
idempotency_key="${repository}:${tag}"
failures=0

notify_target() {
  local target_name="$1"
  local target_url="$2"
  local target_token="$3"

  echo "Notifying SPX WWW ${target_name} about ${repository}@${tag}."
  if ! curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --retry 3 \
    --retry-delay 2 \
    --connect-timeout 10 \
    --max-time 60 \
    -X POST \
    -H "Authorization: Bearer ${target_token}" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: ${idempotency_key}" \
    --data "${payload}" \
    "${target_url}"; then
    echo "SPX WWW ${target_name} sync failed for ${repository}@${tag}." >&2
    failures=$((failures + 1))
  fi
}

if [[ "${staging_enabled}" == "true" ]]; then
  notify_target \
    "staging" \
    "${SPX_WWW_STAGING_DOWNLOAD_SYNC_URL}" \
    "${SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN}"
fi

if [[ "${production_enabled}" == "true" ]]; then
  notify_target \
    "production" \
    "${SPX_WWW_DOWNLOAD_SYNC_URL}" \
    "${SPX_WWW_DOWNLOAD_SYNC_TOKEN}"
fi

if ((failures > 0)); then
  echo "SPX WWW sync failed for ${failures} target(s)." >&2
  exit 1
fi

echo "SPX WWW sync completed for ${repository}@${tag}."
