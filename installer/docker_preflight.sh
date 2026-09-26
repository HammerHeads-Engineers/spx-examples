#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

spx_docker_platform() {
  case "$(uname -s)" in
    Darwin) printf 'macOS\n' ;;
    Linux) printf 'Linux\n' ;;
    *) printf 'Other\n' ;;
  esac
}

spx_resolve_docker_cli() {
  local candidate

  if command -v docker >/dev/null 2>&1; then
    return 0
  fi

  for candidate in \
    "${HOME:-}/.docker/bin/docker" \
    /Applications/Docker.app/Contents/Resources/bin/docker \
    /opt/homebrew/bin/docker \
    /usr/local/bin/docker \
    /usr/bin/docker \
    /snap/bin/docker; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      PATH="$(dirname "${candidate}"):${PATH}"
      export PATH
      command -v docker >/dev/null 2>&1 && return 0
    fi
  done

  return 1
}

spx_docker_daemon_ready() {
  spx_resolve_docker_cli || return 1
  docker info >/dev/null 2>&1
}

spx_wait_for_docker_daemon() {
  local timeout_seconds="${1:-60}"
  local attempt attempts=$(( (timeout_seconds + 1) / 2 ))

  for ((attempt = 0; attempt <= attempts; attempt++)); do
    if spx_docker_daemon_ready; then
      return 0
    fi
    if (( attempt < attempts )); then
      sleep 2
    fi
  done

  return 1
}

spx_start_docker_desktop() {
  local platform="$1"

  if spx_resolve_docker_cli && docker desktop start --detach >/dev/null 2>&1; then
    echo "[spx-install] Requested Docker Desktop startup through the Docker CLI."
    return 0
  fi

  if [[ "${platform}" == "macOS" ]] && command -v open >/dev/null 2>&1; then
    if open -a Docker >/dev/null 2>&1; then
      echo "[spx-install] Opened Docker Desktop. Waiting for Docker Engine..."
      return 0
    fi
  fi

  echo "[spx-install] Docker Desktop could not be started automatically." >&2
  return 1
}

spx_print_docker_detail() {
  local detail="$1"
  local line lowered_line

  while IFS= read -r line; do
    lowered_line="$(printf '%s' "${line}" | tr '[:upper:]' '[:lower:]')"
    if [[ -n "${line}" && "${lowered_line}" != *"errors pretty printing info"* ]]; then
      printf '[spx-install] Docker detail: %s\n' "${line}" >&2
      return 0
    fi
  done <<< "${detail}"
}

spx_desktop_instructions() {
  cat <<'EOF'
Docker Engine is not reachable. Docker Desktop may still be starting or paused.
Open Docker Desktop, unpause it if needed, and wait until Docker Engine is running.
If Docker Desktop is not installed, install it from https://www.docker.com/products/docker-desktop/.
EOF
}

spx_linux_engine_instructions() {
  cat <<'EOF'
Docker Engine is not available.
Install Docker Engine and the Docker Compose plugin using https://docs.docker.com/engine/install/.
On systemd-based Linux distributions, you can start the service with: sudo systemctl start docker
If the daemon reports a permission error, follow Docker's instructions for non-root access.
EOF
}

spx_compose_instructions() {
  local platform="$1"
  if [[ "${platform}" == "Linux" ]]; then
    cat <<'EOF'
Docker Compose is not available.
Install the Docker Compose plugin using https://docs.docker.com/compose/install/linux/.
EOF
  else
    cat <<'EOF'
Docker Compose is not available.
Install or update Docker Desktop from https://www.docker.com/products/docker-desktop/.
Docker Desktop includes the Docker Compose plugin.
EOF
  fi
}

spx_print_recovery_instructions() {
  local failure="$1"
  local platform="$2"
  local detail="$3"
  local lowered_detail
  lowered_detail="$(printf '%s' "${detail}" | tr '[:upper:]' '[:lower:]')"

  case "${failure}" in
    cli)
      if [[ "${platform}" == "Linux" ]]; then
        spx_linux_engine_instructions
      else
        cat <<'EOF'
Docker CLI was not found.
Install Docker Desktop from https://www.docker.com/products/docker-desktop/; it includes the Docker CLI and Compose.
Then open Docker Desktop and wait until Docker Engine is running.
EOF
      fi
      ;;
    daemon)
      if [[ "${lowered_detail}" == *"permission denied"* || "${lowered_detail}" == *"permissionerror"* ]]; then
        echo "Docker CLI is installed, but this account cannot access Docker Engine."
        if [[ "${platform}" == "Linux" ]]; then
          echo "Follow Docker's instructions for non-root access: https://docs.docker.com/engine/install/linux-postinstall/."
          echo "Then sign out and back in before retrying."
        else
          echo "Check that Docker Desktop is running under this account. If access is still denied, ask your administrator to check permissions."
        fi
      elif [[ "${platform}" == "Linux" ]]; then
        spx_linux_engine_instructions
      else
        spx_desktop_instructions
      fi
      ;;
    compose)
      spx_compose_instructions "${platform}"
      ;;
  esac
}

spx_check_docker_state() {
  local platform="$1"
  local docker_info

  if ! spx_resolve_docker_cli; then
    SPX_DOCKER_FAILURE="cli"
    SPX_DOCKER_DETAIL=""
    return 1
  fi

  if ! docker_info="$(docker info 2>&1)"; then
    SPX_DOCKER_FAILURE="daemon"
    SPX_DOCKER_DETAIL="${docker_info}"
    spx_print_docker_detail "${docker_info}"
    return 1
  fi

  if docker compose version >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker compose"
    SPX_DOCKER_FAILURE=""
    SPX_DOCKER_DETAIL=""
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker-compose"
    SPX_DOCKER_FAILURE=""
    SPX_DOCKER_DETAIL=""
    return 0
  fi

  SPX_DOCKER_FAILURE="compose"
  SPX_DOCKER_DETAIL=""
  return 1
}

spx_try_docker_desktop_recovery() {
  local platform="$1"
  local failure="$2"

  if [[ "${platform}" != "macOS" && "${platform}" != "Windows" ]]; then
    return 1
  fi
  if [[ "${failure}" != "cli" && "${failure}" != "daemon" ]]; then
    return 1
  fi

  echo "[spx-install] Docker is not ready. Attempting to start Docker Desktop..."
  if [[ "${failure}" == "cli" ]]; then
    spx_start_docker_desktop "${platform}" || return 1
  else
    spx_start_docker_desktop "${platform}" || true
  fi

  spx_wait_for_docker_daemon 60
}

spx_retry_docker_check() {
  local platform="$1"

  if spx_check_docker_state "${platform}"; then
    return 0
  fi

  local failure="${SPX_DOCKER_FAILURE}"

  if [[ "${failure}" == "cli" || "${failure}" == "daemon" ]]; then
    echo "[spx-install] Waiting up to 60 seconds for Docker CLI and Engine..."
    spx_wait_for_docker_daemon 60 || true
  fi
}

spx_print_headless_recovery_hint() {
  local platform="$1"
  case "${platform}" in
    Linux)
      echo "Run SPX Setup again after Docker Engine and Docker Compose are ready." >&2
      ;;
    *)
      echo "Run SPX Setup again after Docker Desktop and Docker Compose are ready." >&2
      ;;
  esac
}

check_docker() {
  local platform choice failure detail retry_prompt
  platform="$(spx_docker_platform)"

  if spx_check_docker_state "${platform}"; then
    return 0
  fi

  failure="${SPX_DOCKER_FAILURE}"
  detail="${SPX_DOCKER_DETAIL}"
  if [[ "${failure}" == "daemon" && "${platform}" == "Linux" ]]; then
    : # Linux Engine is always started by the user, never by this installer.
  else
    spx_try_docker_desktop_recovery "${platform}" "${failure}" || true
  fi

  if spx_check_docker_state "${platform}"; then
    return 0
  fi

  while true; do
    failure="${SPX_DOCKER_FAILURE}"
    detail="${SPX_DOCKER_DETAIL}"
    spx_print_recovery_instructions "${failure}" "${platform}" "${detail}" >&2

    if [[ ! -t 0 ]]; then
      spx_print_headless_recovery_hint "${platform}"
      return 1
    fi

    if [[ "${failure}" == "compose" ]]; then
      retry_prompt='Press Enter to check Docker CLI, Engine, and Compose again, or type Q to quit: '
    else
      retry_prompt='Press Enter to retry Docker checks (wait up to 60 seconds), or type Q to quit: '
    fi

    if ! IFS= read -r -p "${retry_prompt}" choice; then
      spx_print_headless_recovery_hint "${platform}"
      return 1
    fi

    case "${choice}" in
      Q|q)
        echo "[spx-install] Docker preflight cancelled by the user." >&2
        return 1
        ;;
      "")
        spx_retry_docker_check "${platform}"
        if spx_check_docker_state "${platform}"; then
          return 0
        fi
        ;;
      *)
        echo "[spx-install] ${retry_prompt}" >&2
        ;;
    esac
  done
}

spx_docker_preflight_required() {
  local arg command_name="" has_selector=0 has_start=0 has_no_start=0

  for arg in "$@"; do
    case "${arg}" in
      -h|--help)
        return 1
        ;;
    esac
  done

  [[ $# -gt 0 ]] || return 0
  command_name="$1"
  [[ "${command_name}" == "generate" ]] || return 1

  shift
  for arg in "$@"; do
    case "${arg}" in
      --packages|--profile-ids|--protocols)
        has_selector=1
        ;;
      --packages=*|--profile-ids=*|--protocols=*)
        has_selector=1
        ;;
      --start)
        has_start=1
        ;;
      --no-start)
        has_no_start=1
        ;;
    esac
  done

  (( has_start == 1 )) && return 0
  (( has_no_start == 1 )) && return 1
  (( has_selector == 1 )) && return 1
  return 0
}
