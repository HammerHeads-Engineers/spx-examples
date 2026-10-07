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
from installer.setup_workspace import read_descriptor, current_descriptor


def build_server(workspace, *, toolset="setup"):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    descriptor = read_descriptor(workspace)
    engine = SetupEngine(Path(descriptor["state_root"]), require_conversation=True)
    session_id = descriptor["session_id"]
    engine.get(session_id)
    if toolset not in {"setup", "runtime"}:
        raise ValueError("Unknown SPX MCP toolset")
    server = FastMCP(
        "SPX Setup" if toolset == "setup" else "SPX Runtime",
        instructions=(
            "Install SPX in this workspace, then use its already-registered spx runtime MCP without reconnecting. Start with setup_get_context once: distinguish the current draft from a previous committed installation. Descriptor changes are resolved per call; old explicit session IDs cannot mutate the new draft. Discover the user's application and missing setup details before selecting models/services. Record selection.requirements using requirements_schema. Never default to the full catalog. Preserve the installed library with catalog_scope=preserve, model_ids=null, service_ids=null; dormant catalog models do not require infrastructure. Needed protocols and explicitly requested instances determine services. Keep zero instances unless explicitly requested. setup_plan validates needs, decisions, dependencies and service removals. Never request or disclose the product key. setup_apply requires explicit approval of the current ready plan."
            if toolset == "setup"
            else "Work with the installed SPX runtime. Configuration is resolved "
            "from private committed state for each call, so installation and "
            "credential changes do not require reconnecting MCP."
        ),
    )
    if toolset == "runtime":
        from installer.setup_runtime import register_runtime_tools

        register_runtime_tools(server, workspace)
        return server
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
        # Setup can replace its descriptor while this stdio process remains
        # connected. Explicit IDs still protect already-reviewed plans.
        try:
            current_workspace, current = current_descriptor(workspace)
            current_engine = SetupEngine(
                Path(current["state_root"]), require_conversation=True
            )
            current_id = current["session_id"]
        except (SetupError, OSError, ValueError, TypeError):
            return {
                "ok": False,
                "error": {
                    "code": "SETUP_NOT_READY",
                    "message": "Setup workspace changed or is unavailable. Run SPX Setup to repair it.",
                },
            }
        requested = requested or current_id
        if requested != current_id:
            return {
                "ok": False,
                "error": {
                    "code": "SESSION_MISMATCH",
                    "message": "This session is no longer current. Read setup_get_context and review the current plan.",
                    "details": {"current_session_id": current_id},
                },
            }
        result = invoke(current_engine, action, requested, **arguments)
        if action == "get-context" and result["ok"]:
            result["result"]["workspace"] = {
                "path": str(current_workspace),
                "version": current.get("workspace_version", 0),
                "redirected": Path(workspace).resolve() != current_workspace,
            }
        return result

    @server.tool(annotations=read)
    def setup_get_context(session_id: str = "") -> dict:
        """Start here: current draft, committed installation, needs, defaults and license in one response. No Docker/API probe."""
        return call("get-context", session_id)

    @server.tool(annotations=read)
    def setup_get_session(session_id: str = "") -> dict:
        """Read the public draft and installation state without accessing credentials."""
        return call("get-session", session_id)

    @server.tool(annotations=read)
    def setup_list_options(
        session_id: str = "", compact: bool = True, protocols: list[str] | None = None
    ) -> dict:
        """Read requirements schema and installed scope; full options map models to services/dependencies."""
        return call("list-options", session_id, compact=compact, protocols=protocols)

    @server.tool(annotations=draft)
    def setup_update_selection(session_id: str, selection: dict) -> dict:
        """Record needs and setup decisions in selection.requirements; patch draft choices, never credentials."""
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

    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["stdio", "doctor"])
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--toolset", choices=["setup", "runtime"], default="setup")
    args = parser.parse_args(argv)
    try:
        server = build_server(args.workspace_root, toolset=args.toolset)
        if args.command == "doctor":
            names = [tool.name for tool in asyncio.run(server.list_tools())]
            print(
                json.dumps(
                    {
                        "ok": True,
                        "purpose": args.toolset,
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
