#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SPX_MCP_WORKSPACE_DIR:-}"
SERVER_NAME="${SPX_MCP_SERVER_NAME:-spx}"
WORKSPACE_MODE="${SPX_MCP_WORKSPACE_MODE:-}"
GIT_REMOTE_URL="${SPX_MCP_GIT_REMOTE_URL:-https://github.com/HammerHeads-Engineers/spx-examples.git}"
GIT_BRANCH="${SPX_MCP_GIT_BRANCH:-develop}"
REPLACE_EXISTING_WORKSPACE="${SPX_MCP_REPLACE_EXISTING_WORKSPACE:-0}"

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

is_interactive() {
  [[ -t 0 || -r /dev/tty ]]
}

can_prompt_on_tty() {
  [[ -r /dev/tty ]]
}

tty_echo() {
  local message="$1"
  if can_prompt_on_tty; then
    printf '%s\n' "${message}" > /dev/tty
    return 0
  fi
  printf '%s\n' "${message}"
}

tty_read() {
  local prompt="$1"
  local variable_name="$2"
  if can_prompt_on_tty; then
    printf '%s' "${prompt}" > /dev/tty
    IFS= read -r "${variable_name}" < /dev/tty
    return 0
  fi
  read -r -p "${prompt}" "${variable_name}"
}

workspace_is_git_repo() {
  local workspace_dir="$1"
  [[ -d "${workspace_dir}/.git" ]]
}

workspace_has_entries() {
  local workspace_dir="$1"
  [[ -d "${workspace_dir}" ]] || return 1
  find "${workspace_dir}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q .
}

workspace_needs_replace_for_git_clone() {
  local workspace_dir="$1"
  if workspace_is_git_repo "${workspace_dir}"; then
    return 1
  fi
  if [[ -f "${workspace_dir}" || -L "${workspace_dir}" ]]; then
    return 0
  fi
  workspace_has_entries "${workspace_dir}"
}

normalize_workspace_mode() {
  local mode="$1"
  case "${mode}" in
    managed|git)
      printf '%s\n' "${mode}"
      ;;
    "")
      return 1
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported workspace mode: ${mode}" >&2
      echo "[spx-mcp-setup] Supported values: managed, git" >&2
      exit 1
      ;;
  esac
}

prompt_workspace_mode() {
  local choice=""
  local default_selection="2"
  if workspace_is_git_repo "${WORKSPACE_DIR}"; then
    default_selection="1"
  fi
  while true; do
    tty_echo "[spx-mcp-setup] Choose workspace type:"
    tty_echo "  1. Full git clone of spx-examples (recommended for model contribution and PR flow)"
    tty_echo "  2. Installer-managed MCP workspace copy"
    tty_read "Selection [1/2, default ${default_selection}]: " choice
    case "${choice:-${default_selection}}" in
      1)
        printf '%s\n' "git"
        return 0
        ;;
      2)
        printf '%s\n' "managed"
        return 0
        ;;
    esac
    tty_echo "[spx-mcp-setup] Invalid selection. Choose 1 or 2."
  done
}

confirm_replace_workspace() {
  local workspace_dir="$1"
  local answer=""
  tty_echo "[spx-mcp-setup] The workspace directory already exists and is not a git checkout:"
  tty_echo "  ${workspace_dir}"
  tty_echo "[spx-mcp-setup] Replacing it will delete its current contents before cloning."
  tty_read "Replace it with a fresh git clone? [y/N]: " answer
  case "${answer}" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_workspace_mode() {
  local normalized=""

  normalized="$(normalize_workspace_mode "${WORKSPACE_MODE}" || true)"
  if [[ -n "${normalized}" ]]; then
    printf '%s\n' "${normalized}"
    return 0
  fi

  if ! is_interactive; then
    if workspace_is_git_repo "${WORKSPACE_DIR}"; then
      echo "[spx-mcp-setup] Reusing existing git-backed MCP workspace." >&2
      printf '%s\n' "git"
      return 0
    fi
    printf '%s\n' "managed"
    return 0
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "[spx-mcp-setup] Git is not available, falling back to installer-managed workspace mode." >&2
    printf '%s\n' "managed"
    return 0
  fi

  prompt_workspace_mode
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

WORKSPACE_MODE="$(resolve_workspace_mode)"
if [[ "${WORKSPACE_MODE}" == "managed" ]] && workspace_is_git_repo "${WORKSPACE_DIR}"; then
  echo "[spx-mcp-setup] ${WORKSPACE_DIR} is already a git-backed MCP workspace." >&2
  echo "[spx-mcp-setup] Set SPX_MCP_WORKSPACE_DIR to a different path if you want a managed copy." >&2
  exit 1
fi
if [[ "${WORKSPACE_MODE}" == "git" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "[spx-mcp-setup] Git is required for git-backed workspace mode." >&2
    exit 1
  fi
  if workspace_needs_replace_for_git_clone "${WORKSPACE_DIR}" && [[ "${REPLACE_EXISTING_WORKSPACE}" != "1" ]]; then
    if is_interactive && confirm_replace_workspace "${WORKSPACE_DIR}"; then
      REPLACE_EXISTING_WORKSPACE="1"
    else
      echo "[spx-mcp-setup] Leaving the existing workspace untouched." >&2
      echo "[spx-mcp-setup] Set SPX_MCP_WORKSPACE_DIR to a different path or rerun and confirm replacement." >&2
      exit 1
    fi
  fi
fi

echo "[spx-mcp-setup] Source payload: ${SCRIPT_DIR}"
echo "[spx-mcp-setup] Workspace directory: ${WORKSPACE_DIR}"
echo "[spx-mcp-setup] Workspace mode: ${WORKSPACE_MODE}"
if [[ "${WORKSPACE_MODE}" == "git" ]]; then
  echo "[spx-mcp-setup] Git remote: ${GIT_REMOTE_URL}"
  echo "[spx-mcp-setup] Git branch: ${GIT_BRANCH}"
fi
echo "[spx-mcp-setup] Python runtime: ${MCP_PYTHON}"
if [[ -f "${SEED_ENV_PATH}" ]]; then
  echo "[spx-mcp-setup] Seeding MCP workspace env from: ${SEED_ENV_PATH}"
else
  echo "[spx-mcp-setup] No generated SPX env found. The workspace will use SPX_PRODUCT_KEY=REPLACE_ME."
fi

python_args=(
  "${SCRIPT_DIR}/installer/mcp_workspace.py"
  --source-root "${SCRIPT_DIR}"
  --workspace-dir "${WORKSPACE_DIR}"
  --python "${MCP_PYTHON}"
  --server-name "${SERVER_NAME}"
  --seed-env "${SEED_ENV_PATH}"
  --workspace-mode "${WORKSPACE_MODE}"
)
if [[ "${WORKSPACE_MODE}" == "git" ]]; then
  python_args+=(
    --git-remote-url "${GIT_REMOTE_URL}"
    --git-branch "${GIT_BRANCH}"
  )
  if [[ "${REPLACE_EXISTING_WORKSPACE}" == "1" ]]; then
    python_args+=(--replace-existing-workspace)
  fi
fi

"${MCP_PYTHON}" "${python_args[@]}"

echo ""
echo "[spx-mcp-setup] Codex MCP workspace is ready."
echo "[spx-mcp-setup] Open this folder in Codex and start a fresh thread:"
echo "  ${WORKSPACE_DIR}"

if command -v open >/dev/null 2>&1; then
  open "${WORKSPACE_DIR}" >/dev/null 2>&1 || true
fi
