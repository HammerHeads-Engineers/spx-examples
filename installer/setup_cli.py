"""JSON CLI adapter for the same Setup engine exposed over local MCP."""

import json
from pathlib import Path
import sys

from .setup_session import SetupEngine, SetupError


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "setup",
        help="Plan and execute local Setup sessions (no product-key arguments).",
    )
    parser.add_argument("--state-root", type=Path, default=None)
    actions = parser.add_subparsers(dest="setup_action", required=True)
    for name in (
        "get-session",
        "list-options",
        "update-selection",
        "plan",
        "apply",
        "status",
    ):
        action = actions.add_parser(name)
        action.add_argument("--session-id", required=True)
        action.add_argument(
            "--json",
            action="store_true",
            help="Machine-readable output (also the default).",
        )
        if name == "update-selection":
            action.add_argument(
                "--selection-file",
                required=True,
                help="JSON patch file, or - for stdin",
            )
        if name == "apply":
            action.add_argument("--plan-id", required=True)
            action.add_argument("--revision", required=True, type=int)
        if name == "status":
            action.add_argument("--after-cursor", default=None)
            action.add_argument("--wait-seconds", type=float, default=0)
            action.add_argument("--compact", action="store_true")
        if name == "list-options":
            action.add_argument("--compact", action="store_true")
    return parser


def invoke(engine, action, session_id, **arguments):
    try:
        if action == "get-session":
            value = engine.get(session_id)
        elif action == "status":
            value = engine.status(session_id, **arguments)
        elif action == "list-options":
            value = engine.options(session_id, **arguments)
        elif action == "update-selection":
            value = engine.update(session_id, arguments["selection"])
        elif action == "plan":
            value = engine.plan(session_id)
        elif action == "apply":
            value = engine.apply(
                session_id, arguments["plan_id"], arguments["revision"]
            )
        else:
            raise SetupError("Unknown Setup operation")
        return {"ok": True, "result": value}
    except SetupError as exc:
        return {
            "ok": False,
            "error": {"code": exc.code, "message": str(exc), "details": exc.details},
        }
    except (OSError, ValueError, TypeError):
        return {
            "ok": False,
            "error": {
                "code": "SETUP_ERROR",
                "message": "Setup could not read or validate its local configuration. Run SPX Setup again.",
            },
        }


def run(args):
    try:
        engine = SetupEngine(args.state_root)
        arguments = {}
        if args.setup_action == "update-selection":
            content = (
                sys.stdin.read()
                if args.selection_file == "-"
                else Path(args.selection_file).read_text(encoding="utf-8")
            )
            arguments["selection"] = json.loads(content)
        if args.setup_action == "apply":
            arguments.update(plan_id=args.plan_id, revision=args.revision)
        if args.setup_action == "status":
            arguments.update(
                after_cursor=args.after_cursor,
                wait_seconds=args.wait_seconds,
                compact=args.compact,
            )
        if args.setup_action == "list-options":
            arguments["compact"] = args.compact
        result = invoke(engine, args.setup_action, args.session_id, **arguments)
    except (OSError, ValueError):
        result = {
            "ok": False,
            "error": {
                "code": "SETUP_ERROR",
                "message": "Invalid or inaccessible Setup selection file.",
            },
        }
    # JSON escapes preserve Unicode paths even when a Windows launcher uses
    # a legacy output code page; consumers recover the original string.
    print(json.dumps(result, ensure_ascii=True, default=str))
    return 0 if result["ok"] else 1
