"""Runtime operations and diagnostics using the same tools/configuration as MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spx", description=__doc__)
    parser.add_argument("command", choices=["doctor", "list-tools", "call"])
    parser.add_argument("tool", nargs="?")
    parser.add_argument(
        "--workspace-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--arguments-file", type=Path)
    parser.add_argument("--check-server", action="store_true")
    parser.add_argument("--during-setup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--json", action="store_true", help="JSON is also the default output"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            from installer.setup_runtime import SetupRuntime
            from spx_mcp.cli import doctor_report

            runtime = SetupRuntime(
                args.workspace_root, verify_pending=args.during_setup
            )
            if args.check_server:
                binding, _ = runtime._binding()
                if not binding["started"]:
                    from spx_mcp.errors import RuntimeAvailabilityError

                    raise RuntimeAvailabilityError(
                        "SPX tools are installed; the stack was not started.",
                        "SPX_NOT_STARTED",
                    )
            result = doctor_report(runtime.config, check_server=args.check_server)
        else:
            from installer.setup_mcp import build_server

            server = build_server(args.workspace_root)
            if args.command == "list-tools":
                result = {
                    "ok": True,
                    "tools": [tool.name for tool in asyncio.run(server.list_tools())],
                }
            else:
                if not args.tool:
                    parser.error("call requires a tool name")
                arguments = (
                    json.loads(args.arguments_file.read_text(encoding="utf-8"))
                    if args.arguments_file
                    else {}
                )
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object")
                contents = asyncio.run(server.call_tool(args.tool, arguments))
                if isinstance(contents, tuple):
                    contents = contents[0]
                result = (
                    contents
                    if isinstance(contents, dict)
                    else json.loads(contents[0].text)
                )
        # ASCII JSON escapes preserve Unicode paths across Windows PowerShell
        # code pages as well as UTF-8 agent pipes.
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result.get("ok", False) else 1
    except Exception as error:
        # Raw SDK/OS exceptions can include request credentials. Keep the
        # command diagnostic finite and never disclose their repr/message.
        from spx_mcp.errors import RuntimeAvailabilityError
        from installer.setup_session import SetupError

        safe = isinstance(error, (RuntimeAvailabilityError, SetupError))
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": error.code if safe else "SPX_CLI_ERROR",
                        "message": (
                            str(error)
                            if safe
                            else "SPX command failed. Check the workspace, arguments and API availability."
                        ),
                    },
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
