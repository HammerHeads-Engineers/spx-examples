#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SPX_MCP_WORKSPACE_DIR:-}"
SERVER_NAME="${SPX_MCP_SERVER_NAME:-spx}"

default_workspace_dir() {
  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "${HOME}/Documents/SPX Codex Workspace"
      ;;
    *)
      printf '%s\n' "${HOME}/spx-codex-workspace"
      ;;
  esac
}

default_seed_env() {
  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "${HOME}/Library/Application Support/SPX/generated/.env"
      ;;
    *)
      printf '%s\n' "${HOME}/.local/share/spx/generated/.env"
      ;;
  esac
}

resolve_candidate_path() {
  local candidate="$1"
  if [[ "${candidate}" == */* ]]; then
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
    return 1
  fi

  command -v "${candidate}" 2>/dev/null || return 1
}

python_supports_mcp() {
  local python_bin="$1"
  "${python_bin}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)' >/dev/null 2>&1
}

resolve_mcp_python() {
  local resolved=""
  local candidate=""
  local seen="|"
  local -a candidates=()

  if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidates+=("${PYTHON_BIN}")
  fi
  candidates+=(python3.13 python3.12 python3.11 python3.10 python3 python)

  for candidate in "${candidates[@]}"; do
    resolved="$(resolve_candidate_path "${candidate}" || true)"
    if [[ -z "${resolved}" ]]; then
      continue
    fi
    if [[ "${seen}" == *"|${resolved}|"* ]]; then
      continue
    fi
    seen="${seen}${resolved}|"
    if python_supports_mcp "${resolved}"; then
      printf '%s\n' "${resolved}"
      return 0
    fi
  done

  return 1
}

if [[ -z "${WORKSPACE_DIR}" ]]; then
  WORKSPACE_DIR="$(default_workspace_dir)"
fi

SEED_ENV_PATH="${SPX_MCP_SOURCE_ENV:-$(default_seed_env)}"
MCP_PYTHON="$(resolve_mcp_python || true)"
if [[ -z "${MCP_PYTHON}" ]]; then
  echo "[spx-mcp-setup] Python 3.10+ is required to install the local Codex MCP workspace." >&2
  echo "[spx-mcp-setup] Install Python 3.10+ and rerun this launcher." >&2
  exit 1
fi

echo "[spx-mcp-setup] Source payload: ${SCRIPT_DIR}"
echo "[spx-mcp-setup] Workspace directory: ${WORKSPACE_DIR}"
echo "[spx-mcp-setup] Python runtime: ${MCP_PYTHON}"
if [[ -f "${SEED_ENV_PATH}" ]]; then
  echo "[spx-mcp-setup] Seeding MCP workspace env from: ${SEED_ENV_PATH}"
else
  echo "[spx-mcp-setup] No generated SPX env found. The workspace will use SPX_PRODUCT_KEY=REPLACE_ME."
fi

"${MCP_PYTHON}" "${SCRIPT_DIR}/installer/mcp_workspace.py" \
  --source-root "${SCRIPT_DIR}" \
  --workspace-dir "${WORKSPACE_DIR}" \
  --python "${MCP_PYTHON}" \
  --server-name "${SERVER_NAME}" \
  --seed-env "${SEED_ENV_PATH}"

echo ""
echo "[spx-mcp-setup] Codex MCP workspace is ready."
echo "[spx-mcp-setup] Open this folder in Codex and start a fresh thread:"
echo "  ${WORKSPACE_DIR}"

if command -v open >/dev/null 2>&1; then
  open "${WORKSPACE_DIR}" >/dev/null 2>&1 || true
fi
