#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SPX_MCP_WORKSPACE_DIR:-}"
SERVER_NAME="${SPX_MCP_SERVER_NAME:-spx}"
WORK_MODE="${SPX_MCP_WORK_MODE:-}"
WORKSPACE_KIND="${SPX_MCP_WORKSPACE_KIND:-}"
LEGACY_WORKSPACE_MODE="${SPX_MCP_WORKSPACE_MODE:-}"
GIT_REMOTE_URL="${SPX_MCP_GIT_REMOTE_URL:-https://github.com/HammerHeads-Engineers/spx-examples.git}"
GIT_BRANCH="${SPX_MCP_GIT_BRANCH:-develop}"
REPLACE_EXISTING_WORKSPACE="${SPX_MCP_REPLACE_EXISTING_WORKSPACE:-0}"
CLI_ALLOW_WRITE=""

print_usage() {
  cat <<'EOF'
Usage: spx-mcp-setup.sh [--allow-write | --read-only]

Options:
  --allow-write  Generate the workspace with MCP write tools enabled.
  --read-only    Generate the workspace without MCP write tools.
  -h, --help     Show this help message.

Default behavior:
  Packaged SPX MCP workspaces are generated in read/write mode by default.
EOF
}

parse_cli_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --allow-write)
        CLI_ALLOW_WRITE="1"
        ;;
      --read-only)
        CLI_ALLOW_WRITE="0"
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        echo "[spx-mcp-setup] Unsupported argument: $1" >&2
        print_usage >&2
        exit 1
        ;;
    esac
    shift
  done
}

resolve_allow_write() {
  if [[ -n "${CLI_ALLOW_WRITE}" ]]; then
    printf '%s\n' "${CLI_ALLOW_WRITE}"
    return 0
  fi
  printf '%s\n' "1"
}

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
  [[ -e "${workspace_dir}/.git" ]]
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

normalize_work_mode() {
  local mode="$1"
  case "${mode}" in
    runtime_mcp|repo_dev)
      printf '%s\n' "${mode}"
      ;;
    "")
      return 1
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported work mode: ${mode}" >&2
      echo "[spx-mcp-setup] Supported values: runtime_mcp, repo_dev" >&2
      exit 1
      ;;
  esac
}

normalize_workspace_kind() {
  local workspace_kind="$1"
  case "${workspace_kind}" in
    managed|git)
      printf '%s\n' "${workspace_kind}"
      ;;
    "")
      return 1
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported workspace kind: ${workspace_kind}" >&2
      echo "[spx-mcp-setup] Supported values: managed, git" >&2
      exit 1
      ;;
  esac
}

legacy_workspace_mode_to_work_mode() {
  local legacy_mode="$1"
  case "${legacy_mode}" in
    managed)
      printf '%s\n' "runtime_mcp"
      ;;
    git)
      printf '%s\n' "repo_dev"
      ;;
    "")
      return 1
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported legacy workspace mode: ${legacy_mode}" >&2
      echo "[spx-mcp-setup] Supported values: managed, git" >&2
      exit 1
      ;;
  esac
}

default_work_mode_for_workspace_kind() {
  local workspace_kind="$1"
  case "${workspace_kind}" in
    managed)
      printf '%s\n' "runtime_mcp"
      ;;
    git)
      printf '%s\n' "repo_dev"
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported workspace kind: ${workspace_kind}" >&2
      exit 1
      ;;
  esac
}

work_mode_to_workspace_kind() {
  local mode="$1"
  case "${mode}" in
    runtime_mcp)
      printf '%s\n' "managed"
      ;;
    repo_dev)
      printf '%s\n' "git"
      ;;
    *)
      echo "[spx-mcp-setup] Unsupported work mode: ${mode}" >&2
      exit 1
      ;;
  esac
}

workspace_mode_file_path() {
  local workspace_dir="$1"
  printf '%s\n' "${workspace_dir}/.codex/workspace_mode.toml"
}

workspace_marker_path() {
  local workspace_dir="$1"
  printf '%s\n' "${workspace_dir}/.spx-mcp-workspace.json"
}

read_workspace_local_work_mode() {
  local workspace_dir="$1"
  local mode_file
  mode_file="$(workspace_mode_file_path "${workspace_dir}")"
  [[ -f "${mode_file}" ]] || return 1

  "${MCP_PYTHON}" - "${mode_file}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
pattern = re.compile(r'^mode\s*=\s*"(?P<mode>[^"]+)"\s*$')
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    match = pattern.match(line)
    if match:
        print(match.group("mode"))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

read_workspace_metadata_work_mode() {
  local workspace_dir="$1"
  local marker_path
  marker_path="$(workspace_marker_path "${workspace_dir}")"
  [[ -f "${marker_path}" ]] || return 1

  "${MCP_PYTHON}" - "${marker_path}" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
work_mode = payload.get("default_work_mode")
if isinstance(work_mode, str) and work_mode:
    print(work_mode)
    raise SystemExit(0)

workspace_kind = payload.get("workspace_kind")
if not isinstance(workspace_kind, str) or not workspace_kind:
    workspace_kind = payload.get("workspace_mode")
if workspace_kind == "managed":
    print("runtime_mcp")
    raise SystemExit(0)
if workspace_kind == "git":
    print("repo_dev")
    raise SystemExit(0)
raise SystemExit(1)
PY
}

resolve_explicit_work_mode() {
  local explicit_mode=""
  local explicit_workspace_kind=""

  explicit_mode="$(normalize_work_mode "${WORK_MODE}" || true)"
  if [[ -z "${explicit_mode}" ]]; then
    explicit_mode="$(legacy_workspace_mode_to_work_mode "${LEGACY_WORKSPACE_MODE}" || true)"
  fi
  explicit_workspace_kind="$(normalize_workspace_kind "${WORKSPACE_KIND}" || true)"

  if [[ -n "${explicit_mode}" && -n "${explicit_workspace_kind}" ]]; then
    if [[ "$(work_mode_to_workspace_kind "${explicit_mode}")" != "${explicit_workspace_kind}" ]]; then
      echo "[spx-mcp-setup] Requested work mode and workspace kind disagree." >&2
      echo "[spx-mcp-setup] ${explicit_mode} requires workspace kind $(work_mode_to_workspace_kind "${explicit_mode}")." >&2
      exit 1
    fi
    printf '%s\n' "${explicit_mode}"
    return 0
  fi

  if [[ -n "${explicit_mode}" ]]; then
    printf '%s\n' "${explicit_mode}"
    return 0
  fi

  if [[ -n "${explicit_workspace_kind}" ]]; then
    default_work_mode_for_workspace_kind "${explicit_workspace_kind}"
    return 0
  fi

  return 1
}

resolve_suggested_work_mode() {
  local suggested_mode=""

  suggested_mode="$(read_workspace_local_work_mode "${WORKSPACE_DIR}" || true)"
  suggested_mode="$(normalize_work_mode "${suggested_mode}" || true)"
  if [[ -n "${suggested_mode}" ]]; then
    printf '%s\n' "${suggested_mode}"
    return 0
  fi

  suggested_mode="$(read_workspace_metadata_work_mode "${WORKSPACE_DIR}" || true)"
  suggested_mode="$(normalize_work_mode "${suggested_mode}" || true)"
  if [[ -n "${suggested_mode}" ]]; then
    printf '%s\n' "${suggested_mode}"
    return 0
  fi

  printf '%s\n' "repo_dev"
}

prompt_work_mode() {
  local default_mode="$1"
  local default_selection="2"
  local choice=""

  if [[ "${default_mode}" == "runtime_mcp" ]]; then
    default_selection="1"
  fi

  while true; do
    tty_echo "[spx-mcp-setup] Choose workspace work mode:"
    tty_echo "  1. runtime_mcp  Fast MCP-first workspace for live spx-server work"
    tty_echo "  2. repo_dev     Full git checkout for models, tests, docs, and PRs"
    tty_read "Selection [1/2, default ${default_selection}]: " choice
    case "${choice:-${default_selection}}" in
      1)
        printf '%s\n' "runtime_mcp"
        return 0
        ;;
      2)
        printf '%s\n' "repo_dev"
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

resolve_work_mode() {
  local explicit_mode=""
  local suggested_mode=""

  explicit_mode="$(resolve_explicit_work_mode || true)"
  if [[ -n "${explicit_mode}" ]]; then
    printf '%s\n' "${explicit_mode}"
    return 0
  fi

  suggested_mode="$(resolve_suggested_work_mode)"

  if is_interactive; then
    prompt_work_mode "${suggested_mode}"
    return 0
  fi

  printf '%s\n' "${suggested_mode}"
}

if [[ -z "${WORKSPACE_DIR}" ]]; then
  WORKSPACE_DIR="$(default_workspace_dir)"
fi

parse_cli_args "$@"

SEED_ENV_PATH="${SPX_MCP_SOURCE_ENV:-$(default_seed_env)}"
MCP_PYTHON="$(resolve_mcp_python || true)"
if [[ -z "${MCP_PYTHON}" ]]; then
  echo "[spx-mcp-setup] Python 3.10+ is required to install the local Codex MCP workspace." >&2
  echo "[spx-mcp-setup] Install Python 3.10+ and rerun this launcher." >&2
  exit 1
fi

WORK_MODE="$(resolve_work_mode)"
WORKSPACE_KIND="$(work_mode_to_workspace_kind "${WORK_MODE}")"
ALLOW_WRITE="$(resolve_allow_write)"

if [[ "${WORKSPACE_KIND}" == "managed" ]] && workspace_is_git_repo "${WORKSPACE_DIR}"; then
  echo "[spx-mcp-setup] ${WORKSPACE_DIR} is already a git-backed repo_dev workspace." >&2
  echo "[spx-mcp-setup] Set SPX_MCP_WORKSPACE_DIR to a different path if you want a runtime_mcp managed copy." >&2
  exit 1
fi

if [[ "${WORKSPACE_KIND}" == "git" ]]; then
  if ! workspace_is_git_repo "${WORKSPACE_DIR}" && ! command -v git >/dev/null 2>&1; then
    echo "[spx-mcp-setup] Git is required for repo_dev workspaces." >&2
    echo "[spx-mcp-setup] Install git or rerun and choose runtime_mcp." >&2
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
echo "[spx-mcp-setup] Work mode: ${WORK_MODE}"
echo "[spx-mcp-setup] Workspace kind: ${WORKSPACE_KIND}"
if [[ "${ALLOW_WRITE}" == "1" ]]; then
  echo "[spx-mcp-setup] MCP access mode: read/write"
else
  echo "[spx-mcp-setup] MCP access mode: read-only"
fi
if [[ "${WORKSPACE_KIND}" == "git" ]]; then
  echo "[spx-mcp-setup] Git remote: ${GIT_REMOTE_URL}"
  echo "[spx-mcp-setup] Git branch: ${GIT_BRANCH}"
fi
echo "[spx-mcp-setup] Python runtime: ${MCP_PYTHON}"
if [[ -f "${SEED_ENV_PATH}" ]]; then
  echo "[spx-mcp-setup] Seeding MCP workspace env from: ${SEED_ENV_PATH}"
elif [[ -n "${SPX_PRODUCT_KEY:-}" ]]; then
  echo "[spx-mcp-setup] No generated SPX env found. Seeding MCP workspace from shell environment."
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
  --workspace-kind "${WORKSPACE_KIND}"
  --work-mode "${WORK_MODE}"
)
if [[ "${ALLOW_WRITE}" == "1" ]]; then
  python_args+=(--allow-write)
else
  python_args+=(--read-only)
fi
if [[ "${WORKSPACE_KIND}" == "git" ]]; then
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
echo "[spx-mcp-setup] Open this folder in Codex. The host app reloads MCP config on a fresh thread:"
echo "  ${WORKSPACE_DIR}"

if command -v open >/dev/null 2>&1; then
  open "${WORKSPACE_DIR}" >/dev/null 2>&1 || true
fi
