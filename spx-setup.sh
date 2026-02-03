#!/usr/bin/env bash
set -euo pipefail

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
  bash "./$run_file" "$@"
  exit $?
fi

if [ -f "./spx-install.sh" ]; then
  echo "[spx-setup] Launching spx-install.sh"
  bash "./spx-install.sh" "$@"
  exit $?
fi

echo "[spx-setup] No spx-installer-*.run or spx-install.sh found in $SCRIPT_DIR" >&2
exit 1
