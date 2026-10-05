"""Local stdio Setup server. Runs independently of runtime API and spx_python."""

from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import sys

# Absolute script entrypoints also work when a client starts in a subdirectory.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from installer.setup_cli import invoke
from installer.setup_session import SetupEngine, SetupError
from installer.setup_workspace import read_descriptor


def build_server(workspace):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    descriptor = read_descriptor(workspace)
    engine = SetupEngine(Path(descriptor["state_root"]))
    session_id = descriptor["session_id"]
    engine.get(session_id)
    server = FastMCP(
        "SPX",
        instructions="Install and work with SPX in this same workspace/connection. Before installation use setup_*; after success use repo_* and server_* on user request. Never request or disclose the product key. setup_apply requires explicit approval of the current plan. Runtime tools resolve committed configuration automatically; no reconnect is needed after installation.",
    )
    read = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    draft = ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=False
    )
    apply = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )

    def call(action, requested, **arguments):
        requested = requested or session_id
        if requested != session_id:
            return {
                "ok": False,
                "error": {
                    "code": "SESSION_MISMATCH",
                    "message": "Use the session in this Setup workspace.",
                },
            }
        return invoke(engine, action, requested, **arguments)

    @server.tool(annotations=read)
    def setup_get_session(session_id: str = "") -> dict:
        """Read the public draft and installation state without accessing credentials."""
        return call("get-session", session_id)

    @server.tool(annotations=read)
    def setup_list_options(session_id: str = "", compact: bool = True) -> dict:
        """Use compact for recommended settings and counts; full catalog only for custom choices."""
        return call("list-options", session_id, compact=compact)

    @server.tool(annotations=draft)
    def setup_update_selection(session_id: str, selection: dict) -> dict:
        """Patch draft choices. Never include credentials. Changes invalidate prior plans."""
        return call("update-selection", session_id, selection=selection)

    @server.tool(annotations=draft)
    def setup_plan(session_id: str) -> dict:
        """Validate and present a complete plan, conflicts and notices before approval."""
        return call("plan", session_id)

    @server.tool(annotations=apply)
    def setup_apply(session_id: str, plan_id: str, revision: int) -> dict:
        """After explicit approval in conversation, apply this exact ready plan asynchronously."""
        return call("apply", session_id, plan_id=plan_id, revision=revision)

    @server.tool(annotations=read)
    async def setup_get_status(
        session_id: str,
        after_cursor: str | None = None,
        wait_seconds: float = 0,
        compact: bool = False,
    ) -> dict:
        """Wait up to 30s for a lifecycle/phase change. Reuse cursor; compact omits catalog/log history."""
        return await asyncio.to_thread(
            call,
            "status",
            session_id,
            after_cursor=after_cursor,
            wait_seconds=wait_seconds,
            compact=compact,
        )

    # Publish the stable runtime toolset before installation: the connected
    # client need not rediscover servers/tools when deployment completes.
    from installer.setup_runtime import register_runtime_tools

    register_runtime_tools(server, workspace)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["stdio", "doctor"])
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        server = build_server(args.workspace_root)
        if args.command == "doctor":
            names = [tool.name for tool in asyncio.run(server.list_tools())]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "purpose": "setup",
                        "server_checked": False,
                        "tools": names,
                    }
                )
            )
            return 0
        server.run(transport="stdio")
        return 0
    except (SetupError, OSError, ValueError, ImportError):
        message = {
            "ok": False,
            "error": {
                "code": "SETUP_NOT_READY",
                "message": "Run SPX Setup to prepare a valid local Setup workspace.",
            },
        }
        print(
            json.dumps(message),
            file=sys.stderr if args.command == "stdio" else sys.stdout,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
