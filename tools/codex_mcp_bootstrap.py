#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bootstrap a local Codex MCP config for the current repository."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable, Optional, Sequence, Tuple


DEFAULT_SERVER_NAME = "spx"
DEFAULT_STARTUP_TIMEOUT_SEC = 20
DEFAULT_TOOL_TIMEOUT_SEC = 120


@dataclass(frozen=True)
class ServerInvocation:
    """Codex MCP command invocation."""

    command: str
    args: list[str]
    cwd: str
    startup_timeout_sec: int = DEFAULT_STARTUP_TIMEOUT_SEC
    tool_timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or update a repo-local Codex MCP config for spx_mcp.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root. Defaults to the current project root.",
    )
    parser.add_argument(
        "--server-name",
        default=DEFAULT_SERVER_NAME,
        help="MCP server id written under [mcp_servers.<name>].",
    )
    parser.add_argument(
        "--startup-timeout-sec",
        type=int,
        default=DEFAULT_STARTUP_TIMEOUT_SEC,
        help="Codex startup timeout for the MCP server process.",
    )
    parser.add_argument(
        "--tool-timeout-sec",
        type=int,
        default=DEFAULT_TOOL_TIMEOUT_SEC,
        help="Codex tool timeout for MCP calls.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Generate the config without --allow-write.",
    )
    parser.add_argument(
        "--skip-git-exclude",
        action="store_true",
        help="Do not update the local git exclude file.",
    )
    return parser


def stdio_args(*, allow_write: bool) -> list[str]:
    args = ["-m", "spx_mcp", "stdio"]
    if allow_write:
        args.append("--allow-write")
    return args


def detect_server_invocation(
    repo_root: Path,
    *,
    allow_write: bool,
    startup_timeout_sec: int,
    tool_timeout_sec: int,
    platform_name: Optional[str] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[ServerInvocation, str]:
    """Return the preferred local command for launching spx_mcp."""
    platform_name = platform_name or sys.platform
    which = which or shutil.which
    repo_root = repo_root.resolve()
    args = stdio_args(allow_write=allow_write)

    if platform_name.startswith("win"):
        venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = repo_root / ".venv" / "bin" / "python"

    if venv_python.exists():
        return (
            ServerInvocation(
                command=venv_python.as_posix(),
                args=args,
                cwd=repo_root.as_posix(),
                startup_timeout_sec=startup_timeout_sec,
                tool_timeout_sec=tool_timeout_sec,
            ),
            "local-venv",
        )

    if which("poetry"):
        return (
            ServerInvocation(
                command="poetry",
                args=["run", "python"] + args,
                cwd=repo_root.as_posix(),
                startup_timeout_sec=startup_timeout_sec,
                tool_timeout_sec=tool_timeout_sec,
            ),
            "poetry",
        )

    for candidate in ("python3", "python"):
        if which(candidate):
            return (
                ServerInvocation(
                    command=candidate,
                    args=args,
                    cwd=repo_root.as_posix(),
                    startup_timeout_sec=startup_timeout_sec,
                    tool_timeout_sec=tool_timeout_sec,
                ),
                candidate,
            )

    raise RuntimeError(
        "No suitable Python launcher was found. "
        "Create .venv or install Poetry/Python first."
    )


def render_mcp_server_block(server_name: str, invocation: ServerInvocation) -> str:
    """Render one [mcp_servers.<name>] TOML section."""
    lines = [
        f"[mcp_servers.{server_name}]",
        f"command = {json.dumps(invocation.command)}",
        f"args = {json.dumps(invocation.args)}",
        f"cwd = {json.dumps(invocation.cwd)}",
        f"startup_timeout_sec = {invocation.startup_timeout_sec}",
        f"tool_timeout_sec = {invocation.tool_timeout_sec}",
    ]
    return "\n".join(lines) + "\n"


def upsert_named_mcp_server(config_text: str, server_name: str, block: str) -> str:
    """Insert or replace one named MCP server section in config.toml."""
    section_re = re.compile(
        rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}\]\s*$.*?(?=^\[|\Z)"
    )
    block = block.rstrip() + "\n"

    if section_re.search(config_text):
        updated = section_re.sub(block + "\n", config_text, count=1)
        return updated.rstrip() + "\n"

    if not config_text.strip():
        return block

    return config_text.rstrip() + "\n\n" + block


def ensure_exclude_pattern(exclude_text: str, pattern: str) -> Tuple[str, bool]:
    """Ensure one exclude pattern exists exactly once."""
    normalized = exclude_text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    existing = {line.strip() for line in lines if line.strip()}
    if pattern in existing:
        return exclude_text if exclude_text.endswith(("\n", "\r\n")) else exclude_text + "\n", False

    suffix = "" if not exclude_text or exclude_text.endswith(("\n", "\r\n")) else "\n"
    return exclude_text + suffix + pattern + "\n", True


def resolve_git_exclude_path(repo_root: Path) -> Optional[Path]:
    """Return the effective .git/info/exclude path for this worktree."""
    repo_root = repo_root.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "info/exclude"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    candidate = result.stdout.strip()
    if not candidate:
        return None
    candidate_path = Path(candidate)
    if not candidate_path.is_absolute():
        candidate_path = repo_root / candidate_path
    return candidate_path.resolve()


def bootstrap_codex_mcp(
    *,
    repo_root: Path,
    server_name: str,
    allow_write: bool,
    startup_timeout_sec: int,
    tool_timeout_sec: int,
    update_git_exclude: bool,
) -> dict[str, object]:
    """Create or update the local Codex config and optionally git exclude."""
    repo_root = repo_root.resolve()
    invocation, strategy = detect_server_invocation(
        repo_root,
        allow_write=allow_write,
        startup_timeout_sec=startup_timeout_sec,
        tool_timeout_sec=tool_timeout_sec,
    )

    config_dir = repo_root / ".codex"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    existing_config = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    )
    rendered = render_mcp_server_block(server_name, invocation)
    updated_config = upsert_named_mcp_server(existing_config, server_name, rendered)
    config_changed = updated_config != existing_config
    config_path.write_text(updated_config, encoding="utf-8")

    exclude_path: Optional[Path] = None
    exclude_changed = False
    if update_git_exclude:
        exclude_path = resolve_git_exclude_path(repo_root)
        if exclude_path is not None:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            existing_exclude = (
                exclude_path.read_text(encoding="utf-8")
                if exclude_path.exists()
                else ""
            )
            updated_exclude, exclude_changed = ensure_exclude_pattern(
                existing_exclude,
                ".codex/config.toml",
            )
            if updated_exclude != existing_exclude:
                exclude_path.write_text(updated_exclude, encoding="utf-8")

    return {
        "repo_root": str(repo_root),
        "config_path": str(config_path),
        "config_changed": config_changed,
        "exclude_path": str(exclude_path) if exclude_path else None,
        "exclude_changed": exclude_changed,
        "server_name": server_name,
        "strategy": strategy,
        "allow_write": allow_write,
        "command": invocation.command,
        "args": invocation.args,
        "cwd": invocation.cwd,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = bootstrap_codex_mcp(
            repo_root=Path(args.repo_root),
            server_name=args.server_name,
            allow_write=not args.read_only,
            startup_timeout_sec=args.startup_timeout_sec,
            tool_timeout_sec=args.tool_timeout_sec,
            update_git_exclude=not args.skip_git_exclude,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"repo_root: {result['repo_root']}")
    print(f"config_path: {result['config_path']}")
    print(f"config_changed: {result['config_changed']}")
    print(f"server_name: {result['server_name']}")
    print(f"strategy: {result['strategy']}")
    print(f"allow_write: {result['allow_write']}")
    print(f"command: {result['command']}")
    print(f"args: {json.dumps(result['args'])}")
    if result["exclude_path"]:
        print(f"exclude_path: {result['exclude_path']}")
        print(f"exclude_changed: {result['exclude_changed']}")
    else:
        print("exclude_path: unavailable")
    print("next_step: restart Codex or open a fresh thread in this workspace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
