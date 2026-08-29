#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the MCP stdio transport with an explicitly selected interpreter."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


REQUIRED_TOOLS = {
    "repo_list_packs",
    "server_list_models",
    "server_get_attrs",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", required=True, help="Python executable to run the MCP server."
    )
    parser.add_argument("--repo-root", required=True, help="MCP workspace root.")
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Verify the write-enabled MCP tool surface.",
    )
    return parser.parse_args()


def absolute_path_without_resolving_symlinks(value: str) -> Path:
    """Return an absolute path while preserving a virtualenv launcher symlink.

    On Unix, a virtualenv's ``bin/python`` is commonly a symlink to the host
    interpreter.  Resolving that symlink before spawning the process makes the
    child interpreter lose the virtualenv prefix and can select a different set
    of installed packages.  MCP smoke tests must exercise the exact selected
    runtime, including its virtualenv.
    """

    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


async def verify_transport(
    python_executable: Path,
    repo_root: Path,
    *,
    allow_write: bool,
) -> int:
    server_args = [
        "-m",
        "spx_mcp",
        "stdio",
        "--repo-root",
        str(repo_root),
    ]
    if allow_write:
        server_args.append("--allow-write")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    parameters = StdioServerParameters(
        command=str(python_executable),
        args=server_args,
        env=environment,
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialization = await session.initialize()
            tool_result = await session.list_tools()

    tool_names = {tool.name for tool in tool_result.tools}
    missing_tools = sorted(REQUIRED_TOOLS - tool_names)
    if missing_tools:
        raise RuntimeError(
            "MCP tools/list is missing required tools: " + ", ".join(missing_tools)
        )

    runtime_probe = subprocess.run(
        [
            str(python_executable),
            "-c",
            (
                "import json, platform, sys; "
                "print(json.dumps({'architecture': platform.machine(), "
                "'python_version': '.'.join(map(str, sys.version_info[:3])), "
                "'system': platform.system()}))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    runtime_info = json.loads(runtime_probe.stdout)
    print(
        f"[mcp-smoke] System: {runtime_info['system']} "
        f"({runtime_info['architecture']})"
    )
    print(f"[mcp-smoke] Python version: {runtime_info['python_version']}")
    print(f"[mcp-smoke] Python: {python_executable}")
    print(f"[mcp-smoke] Workspace .venv: {repo_root / '.venv'}")
    print(f"[mcp-smoke] MCP protocol: {initialization.protocolVersion}")
    print(f"[mcp-smoke] Tool count: {len(tool_names)}")
    print("[mcp-smoke] initialize and tools/list passed")
    return 0


def main() -> int:
    args = parse_args()
    python_executable = absolute_path_without_resolving_symlinks(args.python)
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not python_executable.is_file():
        raise RuntimeError(f"Python executable does not exist: {python_executable}")
    if not repo_root.is_dir():
        raise RuntimeError(f"MCP workspace does not exist: {repo_root}")
    return asyncio.run(
        verify_transport(
            python_executable,
            repo_root,
            allow_write=args.allow_write,
        )
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[mcp-smoke] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
