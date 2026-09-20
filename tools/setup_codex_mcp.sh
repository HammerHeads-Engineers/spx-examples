#!/usr/bin/env sh
# SPDX-License-Identifier: MIT
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BOOTSTRAP="$SCRIPT_DIR/codex_mcp_bootstrap.py"

can_run_python() {
  "$1" -c "import sys" >/dev/null 2>&1
}

if [ -x "$REPO_ROOT/.venv/bin/python" ] && can_run_python "$REPO_ROOT/.venv/bin/python"; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
elif [ -f "$REPO_ROOT/.venv/Scripts/python.exe" ] && can_run_python "$REPO_ROOT/.venv/Scripts/python.exe"; then
  PYTHON="$REPO_ROOT/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1 && can_run_python python3; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1 && can_run_python python; then
  PYTHON=python
else
  echo "Python launcher not found. Install python3 or python first." >&2
  exit 1
fi

exec "$PYTHON" "$BOOTSTRAP" --repo-root "$REPO_ROOT" "$@"
