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
    parser.add_argument("--candidate-session-id", help=argparse.SUPPRESS)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Also check whether another project's Codex MCP entries target this SPX workspace.",
    )
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
            if args.candidate_session_id:
                from installer.setup_runtime import candidate_config

                candidate = runtime.engine._read(args.candidate_session_id)
                current = runtime.engine._read(runtime.session_id)
                if (
                    Path(candidate["output"]).resolve()
                    != Path(current["output"]).resolve()
                ):
                    raise ValueError("Candidate installation does not match workspace")
                config = candidate_config(
                    runtime.engine, candidate, args.workspace_root
                )
            else:
                try:
                    config = runtime.config
                except Exception as error:
                    from spx_mcp.errors import RuntimeAvailabilityError

                    if (
                        not args.check_server
                        and isinstance(error, RuntimeAvailabilityError)
                        and error.code == "SPX_NOT_STARTED"
                    ):
                        config = runtime.pending_config()
                    else:
                        raise
            if args.check_server and not args.candidate_session_id:
                binding, _ = runtime._binding()
                if not binding["started"]:
                    from spx_mcp.errors import RuntimeAvailabilityError

                    raise RuntimeAvailabilityError(
                        "SPX tools are installed; the stack was not started.",
                        "SPX_NOT_STARTED",
                    )
            result = doctor_report(config, check_server=args.check_server)
            if args.project_root:
                result["project_mcp"] = project_mcp_check(
                    args.project_root, args.workspace_root
                )
                if not result["project_mcp"]["ok"]:
                    result["ok"] = False
        else:
            from installer.setup_mcp import build_server

            server = build_server(args.workspace_root, toolset="runtime")
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


def project_mcp_check(project_root: Path, workspace_root: Path) -> dict:
    """Report stale project-local Codex entries without printing their contents."""
    path = project_root / ".codex" / "config.toml"
    if not path.is_file():
        return {
            "ok": True,
            "checked": True,
            "message": "No project-local Codex MCP configuration.",
        }
    try:
        try:
            import tomllib as toml_reader
        except ImportError:  # Python 3.10
            import tomli as toml_reader
        with path.open("rb") as handle:
            servers = toml_reader.load(handle).get("mcp_servers", {})
    except (OSError, ValueError, ImportError):
        return {
            "ok": False,
            "checked": True,
            "message": "Project-local Codex MCP configuration is unreadable.",
        }
    expected = workspace_root.resolve()
    stale = []
    for name in ("spx_setup", "spx"):
        entry = servers.get(name)
        if not isinstance(entry, dict):
            continue
        args = entry.get("args", [])
        if not isinstance(args, list) or not any(
            isinstance(item, str) and Path(item).resolve() == expected for item in args
        ):
            stale.append(name)
    if stale:
        return {
            "ok": False,
            "checked": True,
            "message": "Project-local Codex MCP entry points outside the installed SPX workspace: "
            + ", ".join(stale)
            + ". Open the installed workspace or repair this project's MCP configuration.",
        }
    return {
        "ok": True,
        "checked": True,
        "message": "Project-local SPX MCP entries are current.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
