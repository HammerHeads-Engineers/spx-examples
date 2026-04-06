#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_BOOTSTRAP="${REPO_DIR}/installer/runtime_bootstrap.py"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[spx-install] Missing required command: $1" >&2
    exit 1
  fi
}

resolve_system_python() {
  if [ -n "${PYTHON_BIN:-}" ]; then
    printf '%s\n' "${PYTHON_BIN}"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    printf 'python3\n'
    return
  fi

  if command -v python >/dev/null 2>&1; then
    printf 'python\n'
    return
  fi

  echo "[spx-install] Missing required command: python3 or python" >&2
  exit 1
}

resolve_runtime_root() {
  if [ -n "${SPX_RUNTIME_HOME:-}" ]; then
    printf '%s\n' "${SPX_RUNTIME_HOME}"
    return
  fi

  if [ -w "${REPO_DIR}" ]; then
    printf '%s\n' "${REPO_DIR}/.spx-runtime"
    return
  fi

  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "${HOME}/Library/Application Support/SPX/runtime"
      ;;
    *)
      printf '%s\n' "${HOME}/.local/share/spx/runtime"
      ;;
  esac
}

resolve_default_output() {
  if [ -n "${SPX_INSTALLER_OUTPUT_DIR:-}" ]; then
    printf '%s\n' "${SPX_INSTALLER_OUTPUT_DIR}"
    return
  fi

  if [ -w "${REPO_DIR}" ]; then
    printf '%s\n' "${REPO_DIR}/build/spx-generated"
    return
  fi

  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "${HOME}/Library/Application Support/SPX/generated"
      ;;
    *)
      printf '%s\n' "${HOME}/.local/share/spx/generated"
      ;;
  esac
}

bootstrap_python_runtime() {
  local system_python="$1"
  local runtime_root="$2"

  if [ ! -f "${RUNTIME_BOOTSTRAP}" ]; then
    echo "[spx-install] Missing runtime bootstrap helper: ${RUNTIME_BOOTSTRAP}" >&2
    exit 1
  fi

  "$system_python" "${RUNTIME_BOOTSTRAP}" \
    --venv-dir "${runtime_root}/installer" \
    --package pyyaml \
    --package colorama
}

print_python_runtime_hint() {
  case "$(uname -s)" in
    Linux)
      echo "[spx-install] On Ubuntu/Debian, install 'python3-venv' and, if needed, 'python3-pip', then retry." >&2
      ;;
  esac
}

check_docker() {
  need_cmd docker
  if ! docker info >/dev/null 2>&1; then
    echo "[spx-install] Docker daemon not reachable. Start Docker Desktop/service and retry." >&2
    exit 1
  fi
  if docker compose version >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker-compose"
  else
    echo "[spx-install] Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
  fi
}

SYSTEM_PYTHON_BIN="$(resolve_system_python)"
need_cmd "$SYSTEM_PYTHON_BIN"
check_docker
BOOTSTRAP_LOG="$(mktemp)"
trap 'rm -f "$BOOTSTRAP_LOG"' EXIT
if PYTHON_BIN="$(
  bootstrap_python_runtime "$SYSTEM_PYTHON_BIN" "$(resolve_runtime_root)" \
    2>"$BOOTSTRAP_LOG"
)"; then
  :
else
  cat "$BOOTSTRAP_LOG" >&2
  print_python_runtime_hint
  exit 1
fi
if [ ! -x "${PYTHON_BIN}" ]; then
  echo "[spx-install] Python runtime bootstrap did not return an executable interpreter." >&2
  exit 1
fi
export PYTHON_BIN

cd "$REPO_DIR"

if [ $# -eq 0 ]; then
  DEFAULT_OUTPUT_DIR="$(resolve_default_output)"
  echo "[spx-install] Using output directory: ${DEFAULT_OUTPUT_DIR}"
  set -- generate --output "${DEFAULT_OUTPUT_DIR}"
fi

echo "[spx-install] Running installer CLI: $PYTHON_BIN -m installer $*"
"$PYTHON_BIN" -m installer "$@"
