#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Resolve the Python runtime installed by the native SPX macOS package.
# This file is sourced by packaged shell launchers. Portable archives may use
# the same helper, but still fall back to a Python interpreter from PATH.

SPX_MACOS_PYTHON_VERSION="${SPX_MACOS_PYTHON_VERSION:-3.12.10}"
SPX_MACOS_PYTHON_FRAMEWORK_VERSION="${SPX_MACOS_PYTHON_FRAMEWORK_VERSION:-${SPX_MACOS_PYTHON_VERSION%.*}}"
SPX_MACOS_PYTHON_BIN_NAME="${SPX_MACOS_PYTHON_BIN_NAME:-python${SPX_MACOS_PYTHON_FRAMEWORK_VERSION}}"

spx_macos_python_is_usable() {
  local candidate="$1"

  [ -x "${candidate}" ] || return 1
  "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)' \
    >/dev/null 2>&1
}

spx_resolve_macos_python() {
  [ "$(uname -s)" = "Darwin" ] || return 1

  local candidate
  local -a candidates=()

  if [ -n "${SPX_MACOS_PYTHON_BIN:-}" ]; then
    candidates+=("${SPX_MACOS_PYTHON_BIN}")
  fi

  candidates+=(
    "/Library/Frameworks/Python.framework/Versions/${SPX_MACOS_PYTHON_FRAMEWORK_VERSION}/bin/${SPX_MACOS_PYTHON_BIN_NAME}"
  )

  # Keep custom/local builds usable too: the official installer maintains the
  # Current symlink even when the patch version changes. The exact pinned
  # path above always wins for the release package.
  local current_candidate
  for current_candidate in \
    "/Library/Frameworks/Python.framework/Versions/Current/bin/"python3.*; do
    [ -e "${current_candidate}" ] || continue
    candidates+=("${current_candidate}")
  done

  for candidate in "${candidates[@]}"; do
    if spx_macos_python_is_usable "${candidate}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}
