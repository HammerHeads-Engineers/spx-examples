#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

PAUSE_ON_EXIT=0
FORWARDED_ARGS=()
for argument in "$@"; do
  if [ "$argument" = "--pause-on-exit" ]; then
    PAUSE_ON_EXIT=1
  else
    FORWARDED_ARGS+=("$argument")
  fi
done

pause_before_exit() {
  local status="$1"

  if [ "$PAUSE_ON_EXIT" -ne 1 ] || [ ! -t 0 ]; then
    return 0
  fi

  echo ""
  read -r -p "Press ENTER to close..." _ || true
}

run_with_optional_pause() {
  local status

  if "$@"; then
    status=0
  else
    status=$?
  fi
  pause_before_exit "$status"
  return "$status"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

run_file=""
shopt -s nullglob
run_candidates=(spx-installer-*.run)
shopt -u nullglob

if [ ${#run_candidates[@]} -gt 0 ]; then
  run_file=$(printf '%s\n' "${run_candidates[@]}" | sort -V | tail -n 1)
fi

if [ -n "$run_file" ]; then
  echo "[spx-setup] Launching $run_file"
  if [ ${#FORWARDED_ARGS[@]} -gt 0 ]; then
    if run_with_optional_pause bash "./$run_file" "${FORWARDED_ARGS[@]}"; then
      exit 0
    else
      exit $?
    fi
  else
    if run_with_optional_pause bash "./$run_file"; then
      exit 0
    else
      exit $?
    fi
  fi
fi

if [ -f "./spx-install.sh" ]; then
  echo "[spx-setup] Launching spx-install.sh"
  if [ ${#FORWARDED_ARGS[@]} -gt 0 ]; then
    if run_with_optional_pause bash "./spx-install.sh" "${FORWARDED_ARGS[@]}"; then
      exit 0
    else
      exit $?
    fi
  else
    if run_with_optional_pause bash "./spx-install.sh"; then
      exit 0
    else
      exit $?
    fi
  fi
fi

echo "[spx-setup] No spx-installer-*.run or spx-install.sh found in $SCRIPT_DIR" >&2
exit 1
