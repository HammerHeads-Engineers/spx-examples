#!/bin/bash
# SPDX-License-Identifier: MIT

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

LAUNCHER="./spx-setup.sh"
if [ ! -f "$LAUNCHER" ]; then
  if [ -f "./spx-install.sh" ]; then
    LAUNCHER="./spx-install.sh"
  else
    echo "[spx-setup] Missing launcher in $SCRIPT_DIR"
    read -r -p "Press Enter to close..." _
    exit 1
  fi
fi

if command -v xattr >/dev/null 2>&1; then
  shopt -s nullglob
  candidates=(
    "$LAUNCHER"
    "./spx-install.sh"
    ./spx-installer-*.run
  )
  shopt -u nullglob
  for candidate in "${candidates[@]}"; do
    if [ -f "$candidate" ]; then
      xattr -d com.apple.quarantine "$candidate" >/dev/null 2>&1 || true
    fi
  done
fi

bash "$LAUNCHER" "$@"
EXIT_CODE=$?

echo ""
echo "Exit code: $EXIT_CODE"
read -r -p "Press Enter to close..." _

exit $EXIT_CODE
