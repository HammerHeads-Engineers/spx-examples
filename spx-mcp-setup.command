#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

LAUNCHER="./spx-mcp-setup.sh"
if [ ! -f "$LAUNCHER" ]; then
  echo "[spx-mcp-setup] Missing launcher in $SCRIPT_DIR"
  read -r -p "Press Enter to close..." _
  exit 1
fi

if command -v xattr >/dev/null 2>&1; then
  xattr -d com.apple.quarantine "$LAUNCHER" >/dev/null 2>&1 || true
fi

bash "$LAUNCHER" "$@"
EXIT_CODE=$?

echo ""
echo "Exit code: $EXIT_CODE"
read -r -p "Press Enter to close..." _

exit $EXIT_CODE
