"""One private installation binding shared by Setup MCP and the runtime CLI.

The binding is published only after deployment succeeds. An already connected
MCP process resolves it for each operation, never from inherited host variables.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

from .setup_session import SetupEngine, SetupError, atomic_json, _endpoints
from spx_mcp.errors import RuntimeAvailabilityError


def binding_path(engine, output):
    identity = os.path.normcase(str(Path(output).resolve()))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return engine.root / "installations" / digest / "runtime.json"


def publish_runtime(engine, session, *, started):
    atomic_json(
        binding_path(engine, session["output"]),
        {
            "session_id": session["session_id"],
            "api": _endpoints(Path(session["output"]))["api"],
            "started": bool(started),
        },
    )


class SetupRuntime:
    """Adapter for existing SPX tools with fresh private configuration per call."""

    def __init__(self, workspace, *, verify_pending=False):
        from .setup_workspace import read_descriptor

        self.workspace = Path(workspace).resolve()
        descriptor = read_descriptor(self.workspace)
        self.engine = SetupEngine(Path(descriptor["state_root"]))
        self.session_id = descriptor["session_id"]
        self.verify_pending = verify_pending

    @property
    def catalog(self):
        from spx_mcp.backend.catalog import RepoCatalog
        from .setup_workspace import current_descriptor

        workspace, _ = current_descriptor(self.workspace)
        return RepoCatalog(workspace)

    def _binding(self):
        return self._binding_context()[:2]

    def _binding_context(self):
        from .setup_workspace import current_descriptor

        workspace, descriptor = current_descriptor(self.workspace)
        engine = SetupEngine(Path(descriptor["state_root"]))
        session_id = descriptor["session_id"]
        session = engine._read(session_id)
        active = engine.root / "active-installation.json"
        if active.exists():
            owner = json.loads(active.read_text(encoding="utf-8"))
            job_session = engine._read(owner["session_id"])
            if (
                job_session["output"] == session["output"]
                and job_session["status"] in {"APPLYING", "RECOVERY_REQUIRED"}
                and not (
                    self.verify_pending
                    and owner["session_id"] == session_id
                    and job_session["status"] == "APPLYING"
                )
            ):
                raise RuntimeAvailabilityError(
                    "SPX installation is in progress or requires recovery. Use setup_get_status.",
                    "SPX_NOT_READY",
                )
        try:
            binding = json.loads(
                binding_path(engine, session["output"]).read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            raise RuntimeAvailabilityError(
                "Complete SPX installation before using runtime tools.", "SPX_NOT_READY"
            ) from None
        installed = engine._read(binding["session_id"])
        if installed["output"] != session["output"]:
            raise RuntimeAvailabilityError(
                "Installation binding does not match this workspace", "SPX_NOT_READY"
            )
        return binding, installed, engine, workspace

    @property
    def config(self):
        return self._config(*self._binding_context())

    def _config(self, binding, installed, engine=None, workspace=None):
        from spx_mcp.config import SpxMcpConfig
        from .product_key import validate_product_key_format

        key = (engine or self.engine)._key(installed)
        try:
            validate_product_key_format(key)
            status = "valid"
        except ValueError:
            status = "invalid"
        return SpxMcpConfig(
            repo_root=workspace or self.workspace,
            spx_base_url=binding["api"],
            product_key=key,
            product_key_status=status,
            product_key_source="private installation state",
            allow_write=True,
            pretty_errors=False,
            workspace_kind="managed",
            default_work_mode="runtime_mcp",
        )

    def create_client(self):
        binding, installed, engine, workspace = self._binding_context()
        if not binding["started"]:
            raise RuntimeAvailabilityError(
                "SPX tools are installed; the stack was not started. Start SPX before using runtime tools.",
                "SPX_NOT_STARTED",
            )
        from spx_mcp.backend.client import create_spx_client

        return create_spx_client(self._config(binding, installed, engine, workspace))

    def require_write(self):
        # Runtime writes are requested separately from installation approval.
        self._binding()


def register_runtime_tools(server, workspace):
    from spx_mcp.toolsets.connection_tools import (
        register_connection_read_tools,
        register_connection_write_tools,
    )
    from spx_mcp.toolsets.diagnostics_tools import register_diagnostics_tools
    from spx_mcp.toolsets.repo_tools import register_repo_tools
    from spx_mcp.toolsets.server_read_tools import register_server_read_tools
    from spx_mcp.toolsets.server_write_tools import register_server_write_tools

    runtime = SetupRuntime(workspace)
    for register in (
        register_repo_tools,
        register_server_read_tools,
        register_server_write_tools,
        register_connection_read_tools,
        register_connection_write_tools,
        register_diagnostics_tools,
    ):
        register(server, runtime)


def prepare_tools(engine, session, *, started, bootstrap=True):
    """Common post-deployment step, including no-start and ordinary wizard flows."""
    from .mcp_workspace import resolve_default_workspace_dir
    from .setup_workspace import prepare_workspace, read_descriptor
    from .setup_session import clean_environment

    publish_runtime(engine, session, started=started)
    workspace = Path(session.get("workspace") or resolve_default_workspace_dir())
    # Agent handoff prepared the full toolset before deployment. Do not copy
    # running code or rebuild its interpreter underneath the connected client.
    descriptor = workspace / "setup-session.json"
    already_prepared = (
        session.get("workspace")
        and descriptor.is_file()
        and read_descriptor(workspace)["session_id"] == session["session_id"]
    )
    if not already_prepared:
        prepare_workspace(
            workspace,
            engine,
            session["session_id"],
            bootstrap=bootstrap,
            preserve_session=True,
        )
    descriptor = read_descriptor(workspace)
    command = [
        descriptor["python"],
        str(workspace / "installer/spx_cli.py"),
        "doctor",
        "--workspace-root",
        str(workspace),
        "--during-setup",
    ]
    if started:
        command.append("--check-server")
    result = subprocess.run(
        command,
        env=clean_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    report = json.loads(result.stdout)
    if not report["ok"]:
        raise SetupError(
            "SPX tools could not verify their dependencies or authenticated API access. Run SPX MCP Setup to repair the workspace.",
            "MCP_NOT_READY",
        )
    atomic_json(
        Path(session["output"]) / ".spx-tools.json", {"workspace": str(workspace)}
    )
    return {
        "ok": True,
        "workspace": str(workspace),
        "server_checked": bool(started),
        "server_name": "spx",
    }


def mark_runtime_started(seed_env, workspace):
    """Refresh a no-start binding after the supported standalone Start commits."""
    from .mcp_workspace import read_dotenv

    runtime = SetupRuntime(workspace, verify_pending=True)
    session = runtime.engine._read(runtime.session_id)
    path = binding_path(runtime.engine, session["output"])
    if not path.exists():
        return False  # First install publishes its binding in the common final step.
    binding = json.loads(path.read_text(encoding="utf-8"))
    installed = runtime.engine._read(binding["session_id"])
    if Path(installed["output"]).resolve() != Path(seed_env).resolve().parent:
        raise SetupError("Workspace refers to a different installation")
    key = read_dotenv(Path(seed_env)).get("SPX_PRODUCT_KEY", "")
    if key.replace("-", "") != runtime.engine._key(installed).replace("-", ""):
        raise SetupError(
            "Installation credentials changed; run SPX Setup to reconfigure tools"
        )
    binding["started"] = True
    atomic_json(path, binding)
    return True
