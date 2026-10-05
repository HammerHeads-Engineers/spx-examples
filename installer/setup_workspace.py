"""Prepare a local agent workspace without requiring SPX API or Docker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from . import paths
from .mcp_workspace import copy_path, copy_file, read_dotenv, SKIP_ENTRY_NAMES
from .setup_session import (
    SetupEngine,
    SetupError,
    atomic_json,
    clean_environment,
    file_lock,
)
from .wizard import InstallerWizard
from tools.codex_mcp_bootstrap import (
    ServerInvocation,
    render_mcp_server_block,
    upsert_named_mcp_server,
)

SERVER_NAME = "spx_setup"


def default_workspace():
    if os.name == "nt":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "SPX/setup-workspace"
        )
    if sys.platform == "darwin":
        return Path.home() / "Documents/spx-setup-workspace"
    return Path.home() / "spx-setup-workspace"


def default_output():
    if os.name == "nt":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "SPX/generated"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/SPX/generated"
    return Path.home() / ".local/share/SPX/generated"


def read_descriptor(workspace):
    value = json.loads(
        (Path(workspace) / "setup-session.json").read_text(encoding="utf-8")
    )
    if (
        value.get("purpose") != "setup"
        or not value.get("session_id")
        or not value.get("state_root")
    ):
        raise SetupError("Invalid Setup workspace descriptor")
    return value


def _jsonc(content):
    """Remove comments/trailing commas outside strings, preserving setting values."""
    result = []
    i, quoted, escaped = 0, False, False
    while i < len(content):
        char = content[i]
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            result.append(char)
        elif content[i : i + 2] == "//":
            i = content.find("\n", i)
            if i < 0:
                break
            result.append("\n")
        elif content[i : i + 2] == "/*":
            end = content.find("*/", i + 2)
            if end < 0:
                raise SetupError("Invalid OpenCode workspace configuration")
            result.append(" ")
            i = end + 1
        elif char == "," and content[i + 1 :].lstrip().startswith(("}", "]")):
            pass
        else:
            result.append(char)
        i += 1
    # Comments can occur after a trailing comma, so remove commas in a second pass.
    text = "".join(result)
    result, quoted, escaped = [], False, False
    for i, char in enumerate(text):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            result.append(char)
        elif char == "," and text[i + 1 :].lstrip().startswith(("}", "]")):
            continue
        else:
            result.append(char)
    return json.loads("".join(result))


def _read_config(path, *, jsonc=False):
    if not path.exists():
        return {}
    try:
        content = path.read_text(encoding="utf-8-sig")
        value = _jsonc(content) if jsonc else json.loads(content)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise SetupError(
            "Invalid client configuration; existing settings were preserved"
        ) from None


def _atomic_text(path, content):
    import uuid

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        # Windows PowerShell 5 reads scripts without a BOM using the ANSI code page.
        temporary.write_text(
            content, encoding="utf-8-sig" if path.suffix.lower() == ".ps1" else "utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_workspace(
    workspace: Path,
    engine: SetupEngine,
    session_id: str,
    *,
    python=None,
    bootstrap=True,
):
    workspace = workspace.expanduser().absolute()
    source = paths.repo_root()
    marker = workspace / ".spx-setup-workspace.json"
    private_root = engine.root.resolve()
    output = Path(engine.get(session_id)["output"]).resolve()
    resolved = workspace.resolve()
    if private_root.is_relative_to(resolved) or resolved.is_relative_to(private_root):
        raise SetupError(
            "Setup workspace must be separate from private credential state"
        )
    if output.is_relative_to(resolved) or resolved.is_relative_to(output):
        raise SetupError(
            "Setup workspace must be separate from the active installation"
        )
    if workspace.resolve() == source.resolve() or workspace.is_symlink():
        raise SetupError("Setup requires a separate managed workspace")
    if workspace.exists() and any(workspace.iterdir()):
        if not marker.is_file() or _read_config(marker).get("purpose") != "setup":
            raise SetupError(
                "Existing directory is not a managed Setup workspace; choose a different workspace"
            )
        old = _read_config(marker)
        old_session = old.get("session_id")
        if old_session:
            previous_engine = engine
            try:
                if (workspace / "setup-session.json").is_file():
                    old_descriptor = read_descriptor(workspace)
                    previous_engine = SetupEngine(Path(old_descriptor["state_root"]))
                previous = previous_engine.get(old_session)
            except SetupError:
                previous = None
            if previous and previous["status"] in {"APPLYING", "RECOVERY_REQUIRED"}:
                raise SetupError(
                    "An existing Setup workspace job is active or requires recovery; reconnect to that workspace",
                    "SETUP_BUSY",
                )
            if previous and old_session != session_id:
                with file_lock(previous_engine.root / "sessions.lock"):
                    old_state = previous_engine._read(old_session)
                    if old_state["status"] in {"APPLYING", "RECOVERY_REQUIRED"}:
                        raise SetupError(
                            "Existing workspace installation is active; reconnect instead",
                            "SETUP_BUSY",
                        )
                    old_state.update(status="HANDED_BACK", plan=None, job=None)
                    previous_engine._write(old_state)
    if sys.version_info < (3, 10) and bootstrap:
        raise SetupError(
            "Agent Setup requires Python 3.10 or newer. Use legacy Setup or install a supported Python interpreter."
        )
    workspace.mkdir(parents=True, exist_ok=True)
    # Validate every existing client profile before changing any of them.
    claude_path = workspace / ".mcp.json"
    claude = _read_config(claude_path)
    opencode_path = workspace / "opencode.jsonc"
    opencode = _read_config(opencode_path, jsonc=True)
    if (
        not isinstance(claude.get("mcpServers", {}), dict)
        or not isinstance(opencode.get("mcp", {}), dict)
        or not isinstance(opencode.get("mcp", {}).get("servers", {}), dict)
    ):
        raise SetupError(
            "Invalid client configuration; existing settings were preserved"
        )
    # Mark ownership before bootstrap so a failed download can be retried safely.
    atomic_json(marker, {"purpose": "setup", "session_id": session_id})
    # Reuse payload-copy helpers; keep client settings, the venv and runtime workspace.
    for name in (
        "installer",
        "library",
        "profiles",
        "extensions",
        "tools",
        "spx_mcp",
        "docs",
        "pyproject.toml",
        "LICENSE",
    ):
        if (source / name).exists():
            destination = workspace / name
            if destination.is_symlink() or not destination.resolve().is_relative_to(
                workspace.resolve()
            ):
                raise SetupError("Managed workspace payload path is unsafe")
            if destination.is_dir() and (source / name).is_dir():
                import shutil

                def safe_copy(src, dst):
                    if Path(dst).is_symlink() or not Path(dst).resolve().is_relative_to(
                        workspace.resolve()
                    ):
                        raise SetupError("Managed workspace payload path is unsafe")
                    copy_file(src, dst)

                shutil.copytree(
                    source / name,
                    destination,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*SKIP_ENTRY_NAMES),
                    copy_function=safe_copy,
                )
            else:
                copy_path(source / name, destination)
    interpreter = Path(python or sys.executable)
    if bootstrap:
        # Same isolated-runtime bootstrap as SPX MCP Setup, with Setup-only deps.
        result = subprocess.run(
            [
                str(interpreter),
                str(workspace / "installer/runtime_bootstrap.py"),
                "--venv-dir",
                str(workspace / ".venv"),
                "--package",
                "pyyaml",
                "--package",
                "requests",
                "--package",
                "mcp>=1.26,<2",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=clean_environment(),
            check=False,
        )
        if result.returncode:
            raise SetupError(
                "Could not prepare the isolated Setup runtime. Check connectivity and Python, then run SPX Setup again."
            )
        interpreter = Path(result.stdout.strip())
        if not interpreter.is_file():
            raise SetupError("Setup bootstrap did not return a valid interpreter")
    script = workspace / "installer/setup_mcp.py"
    args = [str(script), "stdio", "--workspace-root", str(workspace)]
    codex_path = workspace / ".codex/config.toml"
    existing = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    invocation = ServerInvocation(
        str(interpreter),
        args,
        str(workspace),
        startup_timeout_sec=45,
        tool_timeout_sec=120,
    )
    _atomic_text(
        codex_path,
        upsert_named_mcp_server(
            existing, SERVER_NAME, render_mcp_server_block(SERVER_NAME, invocation)
        ),
    )
    claude.setdefault("mcpServers", {})[SERVER_NAME] = {
        "type": "stdio",
        "command": str(interpreter),
        "args": args,
        "env": {},
    }
    atomic_json(claude_path, claude)
    opencode.setdefault("$schema", "https://opencode.ai/config.json")
    opencode.setdefault("mcp", {}).setdefault("servers", {})[SERVER_NAME] = {
        "type": "local",
        "command": [str(interpreter), *args],
        "cwd": str(workspace),
        "codemode": False,
    }
    atomic_json(opencode_path, opencode)
    descriptor = {
        "purpose": "setup",
        "session_id": session_id,
        "state_root": str(engine.root),
        "python": str(interpreter),
    }
    atomic_json(workspace / "setup-session.json", descriptor)
    atomic_json(marker, {"purpose": "setup", "session_id": session_id})
    _write_instructions(workspace, interpreter, engine.root, session_id)
    with file_lock(engine.root / "sessions.lock"):
        session = engine._read(session_id)
        session["source_root"] = str(workspace)
        session.update(plan=None, status="DRAFT", stage="configuration", job=None)
        engine._write(session)
    if bootstrap:
        verified = subprocess.run(
            [
                str(interpreter),
                str(script),
                "doctor",
                "--workspace-root",
                str(workspace),
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=clean_environment(),
            check=False,
        )
        if verified.returncode:
            raise SetupError(
                "Setup workspace verification failed; run SPX Setup again before handing it to an agent."
            )
    return workspace


def _write_instructions(workspace, interpreter, state_root, session_id):
    instructions = """# SPX conversational Setup

This installer-managed workspace configures SPX; it is not a development checkout.
Read INSTALLATION.md and use the local spx_setup MCP tools. Do not edit installer
code, credentials or generated files, and do not run Docker replacement directly.

1. Read setup_get_session and setup_list_options(compact=true). Use these tools,
   not source-code scans, Docker inventories or credential files. The product key
   is already stored privately. Never ask for it in chat. The public license field
   gives planning limits: Community (CO) allows at most five instances; the server
   still validates entitlement. Do not read or infer the key yourself.
2. Default to Server, UI and the model catalog with zero instances, no instance
   autostart, localhost and normal ports. Use recommended_selection for a new
   unconfigured draft; preserve explicit user choices, including no-start/no-UI.
   Additional protocol services are optional: select them for the user's stated
   use case, or set service_ids=null to resolve services for their chosen scope.
   Ask only unanswered setup decisions in one short group. Do not propose demo
   instances, profiles or autostart as defaults, even for paid licenses. Request
   the full options catalog only for custom selections. Create/run simulations
   later in runtime MCP, on a separate user request.
3. Update the draft once and call setup_plan. Port conflicts return a complete
   suggested_port_mappings patch: propose that patch, never handwrite a range.
   You may set replace_existing=true to prepare a reviewable replacement proposal
   before approval; this only prepares a plan and authorizes no execution. Respect
   any explicit refusal. Include replacement and changed ports in final approval,
   without an extra question merely to prepare the plan. If Docker is unavailable,
   help start it and re-plan; required OS permissions remain user actions.
4. Present a short summary: components/catalog, zero instances, local/LAN access,
   changed ports, whether an existing stack is replaced, and whether it will start.
   Keep full per-port/model details available on request. Obtain one approval of
   this concrete ready plan in chat, then call setup_apply with its plan_id/revision.
   Never infer approval from opening the workspace or the initial setup request.
   Obtain new approval only when the reviewed configuration or installation
   conditions actually change. Never stop a service to silence changing logs.
5. Call setup_get_status(compact=true), then reuse its cursor as after_cursor with
   wait_seconds=30 and compact=true. Wait for phase changes or timeout; do not
   busy-poll or repeatedly fetch the full session/catalog. Report meaningful phase
   changes only, not unchanged status or each registered model. Keep all progress
   and diagnostics in this conversation; do not return to terminal questions.
6. Report success only for SUCCEEDED, with the UI link and runtime workspace.
   FAILED requires reviewing diagnostics and a new plan; RECOVERY_REQUIRED must
   not be retried blindly. A repeated apply of the same plan returns the same job.
   Explain MCP warnings separately. Reconnect to resume after disconnect.

Use the JSON CLI equivalents only if the host cannot connect local MCP. Do not
change global client configuration or request product keys in CLI arguments.
"""
    _atomic_text(workspace / "AGENTS.md", instructions)
    _atomic_text(
        workspace / "CLAUDE.md",
        "# SPX Setup\nRead @AGENTS.md and @INSTALLATION.md before using Setup tools.\n",
    )
    _atomic_text(
        workspace / "INSTALLATION.md",
        f"""# Finish SPX installation with your own agent

Open this directory as a trusted local workspace in Codex, Claude Code, or
OpenCode v2 and say: **Complete SPX setup and installation**.
Restart/reconnect the project's MCP if your client does not reload its configuration.
All further decisions and final approval happen in the conversation. Setup's
terminal is only a progress monitor; R returns to the ordinary wizard before apply.

Your SPX key is outside this workspace. Do not paste keys into the conversation.
Setup MCP works before Docker or SPX API is running. This is not runtime MCP;
after installing use the separate SPX MCP Setup workspace for live product work.

Other local agents can launch `{interpreter}` with arguments
`installer/setup_mcp.py stdio --workspace-root <this directory>` using local stdio.
Without MCP run the local setup-cli launcher with these actions:
`get-session`, `list-options`, `update-selection --selection-file <JSON patch>`,
`plan`, `apply --plan-id <reviewed id> --revision <reviewed revision>`, `status`.
The launcher supplies the private-state location and current session identifier.

ChatGPT web and other cloud chats need a local execution bridge; merely attaching
a directory does not give them access to local stdio or Docker.
""",
    )
    # PowerShell's argument array and POSIX quoting keep paths and user arguments intact.
    args = ["-m", "installer", "setup", "--state-root", str(state_root)]
    ps_args = ", ".join("'" + part.replace("'", "''") + "'" for part in args)
    ps = f"Set-Location -LiteralPath $PSScriptRoot\n$setupArgs = @({ps_args}) + @($args[0]) + @('--session-id', '{session_id}') + @($args | Select-Object -Skip 1)\n& '{str(interpreter).replace(chr(39), chr(39)*2)}' @setupArgs\nexit $LASTEXITCODE\n"
    _atomic_text(workspace / "setup-cli.ps1", ps)
    import shlex

    sh = f'#!/usr/bin/env sh\ncd "$(dirname "$0")" || exit 1\naction="$1"; shift\nexec {shlex.quote(str(interpreter))} -m installer setup --state-root {shlex.quote(str(state_root))} "$action" --session-id {session_id} "$@"\n'
    _atomic_text(workspace / "setup-cli.sh", sh)
    if os.name != "nt":
        (workspace / "setup-cli.sh").chmod(0o755)


def launch_handoff(args, loader):
    output = (
        Path(getattr(args, "output", None) or default_output()).expanduser().absolute()
    )
    engine = SetupEngine()
    workspace = Path(getattr(args, "setup_workspace", None) or default_workspace())
    if (workspace / "setup-session.json").is_file():
        descriptor = read_descriptor(workspace)
        previous = SetupEngine(Path(descriptor["state_root"])).get(
            descriptor["session_id"]
        )
        if previous["status"] in {"APPLYING", "RECOVERY_REQUIRED"}:
            print(
                f"[spx-setup] Reconnect your agent to {workspace}; existing job: {previous['status']}."
            )
            return monitor(
                SetupEngine(Path(descriptor["state_root"])), previous["session_id"]
            )
    # Saved installation key takes precedence over a stale host environment.
    saved = read_dotenv(output / ".env").get("SPX_PRODUCT_KEY", "")
    from .product_key import validate_product_key_format

    try:
        key = validate_product_key_format(saved)
        print("[spx-setup] Reusing the saved product key (hidden).")
    except ValueError:
        key = InstallerWizard(loader=loader, mode="legacy")._prompt_license_key(
            use_environment=False
        )
    initial = {}
    if getattr(args, "no_start", False):
        initial["start"] = False
    if getattr(args, "install_spx_ui", None) is not None:
        initial["install_spx_ui"] = args.install_spx_ui
    if getattr(args, "install_examples", None) is not None:
        initial["install_models"] = args.install_examples
    session = engine.create(
        output,
        key,
        initial=initial,
        catalog=getattr(args, "catalog", None),
        profiles=getattr(args, "profiles", None),
    )
    prepare_workspace(workspace, engine, session["session_id"])
    print(f"\n[spx-setup] Open this directory in your local agent: {workspace}")
    print("[spx-setup] Say: Complete SPX setup and installation")
    print(
        "[spx-setup] All configuration and approval now happen in the conversation. R returns to the ordinary wizard before installation."
    )
    return monitor(engine, session["session_id"])


def monitor(engine, session_id):
    from . import terminal_selection
    import time

    if not terminal_selection.is_interactive():
        return 0
    previous = None
    try:
        while True:
            try:
                current = engine.get(session_id)
            except SetupError as error:
                if error.code != "SETUP_BUSY":
                    raise
                time.sleep(1)
                continue
            message = (
                current["status"],
                current["stage"],
                (
                    current.get("diagnostic")
                    if current["status"] in {"SUCCEEDED", "FAILED", "RECOVERY_REQUIRED"}
                    else current.get("progress", {}).get("last_message")
                ),
            )
            if message != previous:
                print(
                    f"[spx-setup] {current['status']} / {current['stage']}: {message[2] or current.get('diagnostic', '')}"
                )
                previous = message
            if current["status"] in {"SUCCEEDED", "FAILED", "RECOVERY_REQUIRED"}:
                return 0 if current["status"] == "SUCCEEDED" else 1
            if _return_requested():
                try:
                    with file_lock(engine.root / "sessions.lock"):
                        latest = engine._read(session_id)
                        if latest["status"] in {"APPLYING", "RECOVERY_REQUIRED"}:
                            print(
                                "[spx-setup] Installation or recovery is in progress; continue in your agent conversation."
                            )
                        else:
                            latest.update(status="HANDED_BACK", plan=None)
                            engine._write(latest)
                            return None
                except SetupError as error:
                    if error.code != "SETUP_BUSY":
                        raise
                    print(
                        "[spx-setup] Planning is in progress. Press R again after it completes to return to the wizard."
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        print(
            "[spx-setup] Monitor closed. Reconnect your agent to check or finish the session; running jobs continue."
        )
        return 0


def _return_requested():
    if os.name == "nt":
        import msvcrt

        return msvcrt.kbhit() and msvcrt.getwch().lower() == "r"
    import select

    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.readline().strip().lower() == "r"
    return False
