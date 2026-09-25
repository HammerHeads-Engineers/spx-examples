#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

spx_docker_daemon_ready() {
  docker info >/dev/null 2>&1
}

spx_wait_for_docker_daemon() {
  local attempt

  if spx_docker_daemon_ready; then
    return 0
  fi

  for ((attempt = 0; attempt < 30; attempt++)); do
    sleep 2
    if spx_docker_daemon_ready; then
      return 0
    fi
  done

  return 1
}

spx_start_docker_desktop() {
  if docker desktop start --detach >/dev/null 2>&1; then
    echo "[spx-install] Requested Docker Desktop startup through the Docker CLI."
    return 0
  fi

  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    if open -a Docker >/dev/null 2>&1; then
      echo "[spx-install] Opened Docker Desktop. Waiting for its daemon..."
      return 0
    fi
  fi

  echo "[spx-install] Could not start Docker Desktop automatically." >&2
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

  return 0
}

spx_docker_recovery_message() {
  local detail="$1"
  local lowered_detail
  lowered_detail="$(printf '%s' "${detail}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${lowered_detail}" == *"manually paused"* ]]; then
    printf '%s\n' "[spx-install] Docker Desktop is paused or its daemon is unavailable. Unpause Docker Desktop, wait until it is ready, then retry."
  else
    printf '%s\n' "[spx-install] Docker Desktop is not reachable. Install and start Docker Desktop, wait until it is ready, then retry."
  fi
}

check_docker() {
  local platform docker_info recovery_message choice

  need_cmd docker
  platform="$(uname -s)"

  if ! docker_info="$(docker info 2>&1)"; then
    if [[ "${platform}" != "Darwin" ]]; then
      echo "[spx-install] Docker daemon not reachable. Start Docker Desktop/service and retry." >&2
      return 1
    fi

    spx_print_docker_detail "${docker_info}"
    echo "[spx-install] Docker daemon is not reachable. Attempting to start Docker Desktop..."
    spx_start_docker_desktop || true

    if ! spx_wait_for_docker_daemon; then
      docker_info="$(docker info 2>&1 || true)"
      while true; do
        recovery_message="$(spx_docker_recovery_message "${docker_info}")"
        if [[ ! -t 0 ]]; then
          printf '%s Run SPX Setup again after Docker Desktop is ready.\n' "${recovery_message}" >&2
          return 1
        fi

        printf '%s\n' "${recovery_message}" >&2
        if ! IFS= read -r -p 'Press R to retry the Docker connection or Q to quit: ' choice; then
          printf '%s Run SPX Setup again after Docker Desktop is ready.\n' "${recovery_message}" >&2
          return 1
        fi

        case "${choice}" in
          R|r)
            echo "[spx-install] Retrying the Docker connection for up to 60 seconds..."
            if spx_wait_for_docker_daemon; then
              break
            fi
            docker_info="$(docker info 2>&1 || true)"
            spx_print_docker_detail "${docker_info}"
            ;;
          Q|q)
            printf '%s\n' "${recovery_message}" >&2
            return 1
            ;;
          *)
            echo "[spx-install] Enter R to retry or Q to quit." >&2
            ;;
        esac
      done
    fi
  fi

  if docker compose version >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    export DOCKER_COMPOSE="docker-compose"
  else
    echo "[spx-install] Neither 'docker compose' nor 'docker-compose' is available." >&2
    return 1
  fi
}
