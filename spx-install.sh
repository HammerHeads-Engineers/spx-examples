#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "[spx-install] Missing required command: python3 or python" >&2
    exit 1
  fi
fi
REQUIRED_MODULES=(
  "yaml:pyyaml"
  "colorama:colorama"
)

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[spx-install] Missing required command: $1" >&2
    exit 1
  fi
}

check_python_modules() {
  local missing_modules=()
  local install_packages=()
  for entry in "${REQUIRED_MODULES[@]}"; do
    local module="${entry%%:*}"
    local package="${entry##*:}"
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      missing_modules+=("$module")
      install_packages+=("$package")
    fi
  done
  if [ ${#missing_modules[@]} -eq 0 ]; then
    return
  fi

  echo "[spx-install] Missing Python modules: ${missing_modules[*]}. Installing via pip..."
  "$PYTHON_BIN" -m pip install --user "${install_packages[@]}"

  for module in "${missing_modules[@]}"; do
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      echo "[spx-install] Unable to import module '${module}' even after pip install." >&2
      exit 1
    fi
  done
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

need_cmd "$PYTHON_BIN"
check_python_modules
check_docker

cd "$REPO_DIR"

if [ $# -eq 0 ]; then
  set -- generate --output build/spx-generated
fi

echo "[spx-install] Running installer CLI: $PYTHON_BIN -m installer $*"
"$PYTHON_BIN" -m installer "$@"
