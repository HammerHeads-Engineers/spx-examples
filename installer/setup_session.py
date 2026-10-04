"""Durable, local Setup sessions shared by CLI, wizard and MCP.

Public documents contain selections and diagnostics, never credentials. Planning
uses a private staging directory; the active bundle is changed only by a job.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import yaml

from . import paths
from .generator import DeploymentGenerator
from .manifest import ManifestLoader
from .network import discover_ipv4_addresses, is_local_bind_address
from .product_key import validate_product_key_format
from .selection import (
    apply_platform_compatibility,
    resolve_model_ids,
    resolve_service_ids,
    resolve_protocol_service_ids,
    resolve_default_instances,
)
from .stack_manager import StackManager, StackManagerError
from .wizard import WizardSelection

DEFAULTS = {
    "packages": [],
    "profiles": [],
    "protocols": [],
    "install_models": True,
    "install_instances": False,
    "install_spx_ui": True,
    "start": True,
    "model_ids": None,
    "service_ids": None,
    "instances": None,
    "start_instances": [],
    "service_bind_addresses": {},
    "port_mappings": {},
    "replace_existing": False,
}
TERMINAL = {"SUCCEEDED", "FAILED", "RECOVERY_REQUIRED"}


class SetupError(RuntimeError):
    def __init__(self, message, code="INVALID_SETUP", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def default_state_root() -> Path:
    if os.name == "nt":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "SPX/setup-state"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/SPX/setup-state"
    return Path.home() / ".local/share/SPX/setup-state"


def private_directory(path: Path) -> None:
    fresh = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SetupError("Private Setup state cannot be a symbolic link")
    if os.name == "nt" and fresh:
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )
        sid = next(csv.reader(io.StringIO(result.stdout.strip())))[1]
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
    elif os.name != "nt":
        path.chmod(0o700)


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            if os.name != "nt":
                temporary.chmod(0o600)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path):
    """Kernel lock: released even when a CLI/MCP process exits unexpectedly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            for _ in range(100):
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise SetupError("Setup is busy; retry shortly", "SETUP_BUSY")
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def artifact_files(root: Path):
    if not root.exists():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and not any(
            part in {"data", "logs", ".spx-runtime", "__pycache__", ".venv"}
            for part in p.relative_to(root).parts
        )
        and not p.name.startswith(".docker-compose.transaction.")
    )


def artifact_digest(root: Path) -> str:
    return _digest(
        [
            (p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
            for p in artifact_files(root)
        ]
    )


def resolve_selection(
    value: dict, key: str, index
) -> tuple[WizardSelection, list[str]]:
    """Resolve and validate a secret-free draft against the shipped catalog."""
    for field in (
        "install_models",
        "install_instances",
        "install_spx_ui",
        "start",
        "replace_existing",
    ):
        if type(value[field]) is not bool:
            raise SetupError(f"{field} must be a boolean")
    for field, available in (
        ("packages", index.industries),
        ("profiles", index.profiles),
        (
            "protocols",
            {p for m in index.models.values() for p in m.protocols}
            | {s.protocol for s in index.services.values()},
        ),
        ("model_ids", index.models),
        ("service_ids", index.services),
    ):
        selected = value[field]
        if selected is None and field in {"model_ids", "service_ids"}:
            continue
        if not isinstance(selected, list) or any(
            not isinstance(item, str) or item not in available for item in selected
        ):
            raise SetupError(f"Invalid {field}; use setup_list_options")
    models = value["model_ids"]
    if models is None:
        models = resolve_model_ids(
            value["packages"], value["profiles"], value["protocols"], index
        )
    if not value["install_models"]:
        models = []
    services = value["service_ids"]
    if services is None:
        services = (
            resolve_protocol_service_ids(value["protocols"], index)
            if value["protocols"] and not value["packages"]
            else resolve_service_ids(
                models, value["packages"], value["profiles"], index
            )
        )
    instances = value["instances"]
    if instances is None:
        instances = (
            resolve_default_instances(value["packages"], index)
            if value["install_instances"]
            else []
        )
    if not isinstance(instances, list):
        raise SetupError("instances must be a list")
    keys = set()
    for entry in instances:
        if (
            not isinstance(entry, dict)
            or entry.get("model_id") not in models
            or not isinstance(entry.get("instance_key"), str)
            or not entry["instance_key"]
        ):
            raise SetupError(
                "Every instance must reference a selected model and have an instance_key"
            )
        if entry["instance_key"] in keys:
            raise SetupError("Duplicate instance_key")
        keys.add(entry["instance_key"])
    start = value["start_instances"]
    if not isinstance(start, list) or any(item not in keys for item in start):
        raise SetupError("start_instances must reference selected instances")
    bindings = value["service_bind_addresses"]
    if not isinstance(bindings, dict) or any(
        s not in services or not isinstance(a, str) or not is_local_bind_address(a)
        for s, a in bindings.items()
    ):
        raise SetupError(
            "Service bind addresses must belong to selected services and this host"
        )
    adjusted = apply_platform_compatibility(
        model_ids=models,
        service_ids=services,
        instances=instances,
        start_instances=start,
        index=index,
    )
    return (
        WizardSelection(
            packages=value["packages"],
            profiles=value["profiles"],
            protocols=value["protocols"],
            install_examples=value["install_models"],
            install_spx_ui=value["install_spx_ui"],
            offline_bundle=not value["start"],
            license_key=key,
            model_ids=adjusted.model_ids,
            service_ids=adjusted.service_ids,
            instances=adjusted.instances,
            start_instances=adjusted.start_instances,
            service_bind_addresses={
                s: bindings.get(s, "127.0.0.1") for s in adjusted.service_ids
            },
        ),
        adjusted.warnings,
    )


class SetupEngine:
    def __init__(self, state_root: Path | None = None):
        self.root = (state_root or default_state_root()).expanduser().absolute()
        private_directory(self.root)

    def _directory(self, session_id):
        if not re.fullmatch(r"[a-f0-9]{32}", str(session_id)):
            raise SetupError("Invalid Setup session identifier")
        path = self.root / session_id
        if not (path / "session.json").is_file() or path.is_symlink():
            raise SetupError("Setup session not found", "SESSION_NOT_FOUND")
        return path

    def _read(self, session_id):
        return json.loads(
            (self._directory(session_id) / "session.json").read_text(encoding="utf-8")
        )

    def _write(self, session):
        atomic_json(self._directory(session["session_id"]) / "session.json", session)

    def create(
        self,
        output: Path,
        product_key: str,
        *,
        initial=None,
        catalog=None,
        profiles=None,
        validate_key=True,
    ):
        # Artifact-only legacy CLI retains its explicit allow-missing behavior.
        # Agent handoff always uses the default strict validation.
        key = validate_product_key_format(product_key) if validate_key else product_key
        session_id = uuid.uuid4().hex
        directory = self.root / session_id
        private_directory(directory)
        # Secret lives exclusively in private state, never in the agent workspace.
        atomic_json(directory / "credential.json", {"product_key": key})
        session = {
            "session_id": session_id,
            "revision": 0,
            "status": "DRAFT",
            "stage": "configuration",
            "output": str(output.expanduser().absolute()),
            "selection": dict(DEFAULTS),
            "source_root": str(paths.repo_root()),
            "catalog": str(catalog) if catalog else None,
            "profiles": str(profiles) if profiles else None,
            "plan": None,
            "job": None,
        }
        atomic_json(directory / "session.json", session)
        if initial is not None:
            return self.update(session_id, initial)
        return self.get(session_id)

    def _key(self, session):
        return json.loads(
            (self._directory(session["session_id"]) / "credential.json").read_text(
                encoding="utf-8"
            )
        )["product_key"]

    def _index(self, session):
        return ManifestLoader(
            catalog_dir=session["catalog"], profiles_dir=session["profiles"]
        ).load()

    def get(self, session_id):
        with file_lock(self.root / "sessions.lock"):
            session = self._read(session_id)
            job = session.get("job")
            if (
                session["status"] == "APPLYING"
                and job
                and job.get("pid")
                and not _pid_alive(job["pid"])
            ):
                session.update(
                    status="RECOVERY_REQUIRED",
                    stage="recovery",
                    diagnostic="Setup worker exited before recording a final result. Do not retry blindly; inspect the transaction and retained backup.",
                )
                self._write(session)
            public = {
                k: v
                for k, v in session.items()
                if k not in {"source_root", "catalog", "profiles"}
            }
            if public.get("plan"):
                public["plan"] = {
                    k: v for k, v in public["plan"].items() if not k.startswith("_")
                }
            progress = self._directory(session_id) / "progress.json"
            if progress.is_file():
                public["progress"] = json.loads(progress.read_text(encoding="utf-8"))
            diagnostics = self._directory(session_id) / "diagnostics.json"
            if diagnostics.is_file():
                public["diagnostics"] = json.loads(
                    diagnostics.read_text(encoding="utf-8")
                )
            return public

    def options(self, session_id):
        session = self._read(session_id)
        index = self._index(session)
        return {
            "packages": [asdict(v) for v in index.industries.values()],
            "profiles": [
                {"id": v.id, "name": v.name, "package": v.pack_id}
                for v in index.profiles.values()
            ],
            "models": [
                {"id": v.id, "name": v.name, "protocols": v.protocols}
                for v in index.models.values()
            ],
            "protocols": sorted(
                {p for m in index.models.values() for p in m.protocols}
                | {s.protocol for s in index.services.values()}
            ),
            "services": [
                {
                    "id": v.id,
                    "name": v.name,
                    "protocol": v.protocol,
                    "ports": [asdict(p) for p in v.ports],
                }
                for v in index.services.values()
            ],
            "local_addresses": [asdict(v) for v in discover_ipv4_addresses()],
        }

    def update(self, session_id, patch):
        with file_lock(self.root / "sessions.lock"):
            session = self._read(session_id)
            if session["status"] in {"APPLYING", "RECOVERY_REQUIRED", "HANDED_BACK"}:
                raise SetupError(
                    "An installation or recovery is already in progress", "SETUP_BUSY"
                )
            if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
                raise SetupError(
                    "Unknown selection fields; credentials cannot be passed to Setup tools"
                )
            encoded = json.dumps(patch)
            key = self._key(session)
            if (
                key in encoded
                or key.replace("-", "") in encoded
                or re.search(r"(?i)product.?key|license.?key", encoded)
            ):
                raise SetupError("Do not pass product keys in Setup tool arguments")
            selection = {**session["selection"], **patch}
            resolve_selection(selection, key, self._index(session))
            session.update(
                selection=selection,
                revision=session["revision"] + 1,
                plan=None,
                status="DRAFT",
                stage="configuration",
                job=None,
            )
            for name in ("diagnostic", "endpoints", "mcp_warning"):
                session.pop(name, None)
            for name in ("progress.json", "diagnostics.json"):
                (self._directory(session_id) / name).unlink(missing_ok=True)
            self._write(session)
        return self.get(session_id)

    def _generate(self, session):
        directory = (
            self._directory(session["session_id"]) / f"stage-{session['revision']}"
        )
        selection, warnings = resolve_selection(
            session["selection"], self._key(session), self._index(session)
        )
        DeploymentGenerator(self._index(session)).generate(selection, directory)
        _map_ports(directory, session["selection"]["port_mappings"])
        _validate_ports(directory)
        env = directory / ".env"
        env.write_text(
            env.read_text(encoding="utf-8")
            + f"\nSPX_BASE_URL={_endpoints(directory)['api']}\n",
            encoding="utf-8",
        )
        return directory, selection, warnings

    def _preflight(self, directory, start):
        from .modbus_port_configurator import (
            _ports_from_compose,
            _tcp_ports_from_compose,
        )

        compose = yaml.safe_load(
            (directory / "docker-compose.generated.yml").read_text(encoding="utf-8")
        )
        ports = _ports_from_compose(compose)
        mappings = _port_options(compose)
        if not start:
            return {
                "checked": False,
                "existing": [],
                "conflicts": {},
                "port_options": mappings,
                "errors": [],
            }
        try:
            from functools import partial

            manager = StackManager(
                directory / "docker-compose.generated.yml",
                directory / ".env",
                runner=partial(subprocess.run, env=clean_environment()),
            )
            result = manager.preflight(
                ports, required_tcp_ports=_tcp_ports_from_compose(compose)
            )
            existing = [
                {
                    "project": stack.project,
                    "containers": [
                        {"id": c.id, "name": c.name, "image": c.image, "state": c.state}
                        for c in stack.containers
                    ],
                }
                for stack in result.existing
                if stack.source != "snapshot"
            ]
            unavailable = set(result.occupied_ports) | set(ports)
            conflicts = [
                {
                    "port": port,
                    "owners": owners,
                    "suggested_host_port": _suggest_port(
                        max(1024, port + 1), unavailable
                    ),
                }
                for port, owners in sorted(result.unrelated_conflicts.items())
            ]
            return {
                "checked": True,
                "existing": existing,
                "conflicts": conflicts,
                "port_options": mappings,
                "errors": [],
            }
        except (StackManagerError, OSError) as exc:
            return {
                "checked": False,
                "existing": [],
                "conflicts": {},
                "port_options": mappings,
                "errors": [
                    {
                        "code": "DOCKER_NOT_READY",
                        "message": "Docker CLI, Engine and Compose must be available before applying. Start Docker Desktop/Engine and request a new plan.",
                    }
                ],
            }

    def plan(self, session_id):
        with file_lock(self.root / "sessions.lock"):
            session = self._read(session_id)
            if session["status"] in {"APPLYING", "RECOVERY_REQUIRED", "HANDED_BACK"}:
                raise SetupError(
                    "Setup is already applying or requires recovery", "SETUP_BUSY"
                )
            directory, selection, warnings = self._generate(session)
            preflight = self._preflight(directory, session["selection"]["start"])
            errors = list(preflight["errors"])
            if (Path(session["output"]) / ".spx-stack-snapshot.json").exists():
                errors.append(
                    {
                        "code": "RECOVERY_REQUIRED",
                        "message": "A previous stack transaction retained its recovery snapshot. Inspect rollback diagnostics before replacing this installation.",
                    }
                )
            if preflight["conflicts"]:
                errors.append(
                    {
                        "code": "PORT_CONFLICT",
                        "message": "Choose alternate host ports using port_mappings, then request a new plan.",
                    }
                )
            if preflight["existing"] and not session["selection"]["replace_existing"]:
                errors.append(
                    {
                        "code": "REPLACEMENT_REQUIRED",
                        "message": "Ask the user whether to replace the detected SPX stack; update replace_existing and request a new plan.",
                    }
                )
            summary = asdict(selection)
            summary.pop("license_key")
            plan = {
                "plan_id": uuid.uuid4().hex,
                "revision": session["revision"],
                "ready": not errors,
                "selection": summary,
                "start": session["selection"]["start"],
                "replace_existing": session["selection"]["replace_existing"],
                "output": session["output"],
                "preflight": preflight,
                "warnings": warnings,
                "errors": errors,
                "notices": __import__("installer.wizard", fromlist=["InstallerWizard"])
                .InstallerWizard()
                ._build_runtime_notices(
                    service_ids=selection.service_ids,
                    install_spx_ui=selection.install_spx_ui,
                    index=self._index(session),
                ),
                "_stage": str(directory),
                "_stage_digest": artifact_digest(directory),
                "_output_digest": artifact_digest(Path(session["output"])),
                "_source_digest": _source_digest(session),
                "_preflight_digest": _digest(preflight),
            }
            session.update(plan=plan, status="PLANNED", stage="review")
            self._write(session)
        return self.get(session_id)["plan"]

    def _validate_plan(self, session, plan_id, revision):
        plan = session.get("plan")
        if (
            not plan
            or plan["plan_id"] != plan_id
            or revision != session["revision"]
            or not plan["ready"]
        ):
            raise SetupError(
                "A current, ready plan must be reviewed and approved in conversation",
                "STALE_PLAN",
            )
        directory = Path(plan["_stage"])
        selection, _ = resolve_selection(
            session["selection"], self._key(session), self._index(session)
        )
        preflight = self._preflight(directory, session["selection"]["start"])
        if (
            artifact_digest(directory) != plan["_stage_digest"]
            or artifact_digest(Path(session["output"])) != plan["_output_digest"]
            or _source_digest(session) != plan["_source_digest"]
            or _digest(preflight) != plan["_preflight_digest"]
        ):
            raise SetupError(
                "Installation conditions changed; request and approve a new plan",
                "STALE_PLAN",
            )
        return plan

    def _operation_file(self, output):
        # SPX uses fixed container names: serialize jobs globally as well as per output.
        return self.root / "active-installation.json"

    def apply(self, session_id, plan_id, revision, *, launch=True):
        with file_lock(self.root / "sessions.lock"):
            session = self._read(session_id)
            if (
                session.get("job")
                and session["job"]["plan_id"] == plan_id
                and revision == session["revision"]
            ):
                return session["job"]  # Idempotency also covers completed operations.
            self._validate_plan(session, plan_id, revision)
            active = self._operation_file(session["output"])
            if active.exists():
                owner = json.loads(active.read_text(encoding="utf-8"))
                previous = self._read(owner["session_id"])
                if (
                    previous.get("job")
                    and previous["job"]["job_id"] == owner["job_id"]
                    and previous["status"] not in {"SUCCEEDED", "FAILED"}
                ):
                    raise SetupError(
                        "Another installation is active or requires recovery",
                        "SETUP_BUSY",
                    )
            job = {"job_id": uuid.uuid4().hex, "plan_id": plan_id, "pid": os.getpid()}
            session.update(job=job, status="APPLYING", stage="queued")
            self._write(session)
            atomic_json(active, {"session_id": session_id, "job_id": job["job_id"]})
            if launch:
                try:
                    command = [
                        sys.executable,
                        "-m",
                        "installer.setup_worker",
                        "--state-root",
                        str(self.root),
                        "--session-id",
                        session_id,
                        "--job-id",
                        job["job_id"],
                    ]
                    if os.name == "nt":
                        allowed = {
                            "PATH",
                            "PATHEXT",
                            "COMSPEC",
                            "SYSTEMROOT",
                            "WINDIR",
                            "TEMP",
                            "TMP",
                            "USERPROFILE",
                            "LOCALAPPDATA",
                            "APPDATA",
                            "HOME",
                            "HTTP_PROXY",
                            "HTTPS_PROXY",
                            "NO_PROXY",
                            "REQUESTS_CA_BUNDLE",
                            "SSL_CERT_FILE",
                            "SSL_CERT_DIR",
                        }
                        atomic_json(
                            self._directory(session_id) / "execution-environment.json",
                            {
                                k: v
                                for k, v in clean_environment().items()
                                if k.upper() in allowed
                            },
                        )
                        launched = subprocess.run(
                            [
                                "powershell.exe",
                                "-NoProfile",
                                "-ExecutionPolicy",
                                "Bypass",
                                "-File",
                                str(
                                    Path(session["source_root"])
                                    / "installer/setup_worker_launch.ps1"
                                ),
                                "-PythonExecutable",
                                sys.executable,
                                "-StateRoot",
                                str(self.root),
                                "-SessionId",
                                session_id,
                                "-JobId",
                                job["job_id"],
                                "-WorkingDirectory",
                                session["source_root"],
                            ],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=20,
                            check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            env=clean_environment(),
                        )
                        job["pid"] = json.loads(launched.stdout)["pid"]
                    else:
                        process = subprocess.Popen(
                            command,
                            cwd=session["source_root"],
                            env=clean_environment(),
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                        )
                        job["pid"] = process.pid
                    session["job"] = job
                    self._write(session)
                except (OSError, subprocess.SubprocessError, ValueError, KeyError):
                    session.update(
                        status="FAILED",
                        stage="launch",
                        diagnostic="Could not launch the Setup worker; no active files were changed.",
                    )
                    self._write(session)
                    raise SetupError(
                        "Could not launch the Setup worker", "WORKER_FAILED"
                    )
            return job

    def run_job(self, session_id, job_id, *, start_callback=None):
        directory = self._directory(session_id)
        with file_lock(directory / "worker.lock"):
            with file_lock(self.root / "sessions.lock"):
                session = self._read(session_id)
                if not session.get("job") or session["job"]["job_id"] != job_id:
                    raise SetupError("Unknown Setup job")
                if session["status"] != "APPLYING":
                    return
                try:
                    self._validate_plan(
                        session, session["job"]["plan_id"], session["revision"]
                    )
                except SetupError:
                    session.update(
                        status="FAILED",
                        stage="preflight",
                        diagnostic="Plan changed before execution; active files were not modified. Request a new plan.",
                    )
                    self._write(session)
                    return
                session["stage"] = "installing"
                self._write(session)
            output = Path(session["output"])
            stage = Path(session["plan"]["_stage"])
            backup = directory / f"backup-{job_id}"
            changed = []
            try:
                previous_api = (
                    _endpoints(output)["api"]
                    if (output / "docker-compose.generated.yml").is_file()
                    else None
                )
            except (ValueError, KeyError, TypeError, OSError):
                previous_api = None
            journal = {
                "output": str(output.absolute()),
                "backup": str(backup),
                "previous_api_url": previous_api,
                "files": changed,
            }
            try:
                private_directory(backup)
                output.mkdir(parents=True, exist_ok=True)
                (output / "data/snapshots").mkdir(parents=True, exist_ok=True)
                for source in artifact_files(stage):
                    relative = source.relative_to(stage)
                    destination = output / relative
                    if (
                        destination.resolve().is_relative_to(output.resolve()) is False
                        or destination.is_symlink()
                    ):
                        raise SetupError(
                            "An installation file escapes the output directory"
                        )
                    existed = destination.exists()
                    if existed:
                        saved = backup / relative
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(destination, saved)
                    changed.append({"path": relative.as_posix(), "existed": existed})
                    atomic_json(backup / "changes.json", journal)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_name(
                        f".{destination.name}.{job_id}.tmp"
                    )
                    shutil.copy2(source, temporary)
                    temporary.replace(destination)
                if start_callback is not None:
                    if not start_callback(output, backup / "changes.json"):
                        raise SetupError("Stack installation failed", "INSTALL_FAILED")
                elif session["selection"]["start"]:
                    self._execute_stack(session, output)
                with file_lock(self.root / "sessions.lock"):
                    session = self._read(session_id)
                    session.update(
                        status="SUCCEEDED",
                        stage="complete",
                        diagnostic=(
                            "SPX started successfully."
                            if session["selection"]["start"] or start_callback
                            else "Configuration generated; stack was not started."
                        ),
                    )
                    session["endpoints"] = _endpoints(stage)
                    self._write(session)
            except Exception:
                restored = True
                for entry in reversed(changed):
                    destination = output / entry["path"]
                    try:
                        if entry["existed"]:
                            shutil.copy2(backup / entry["path"], destination)
                        else:
                            destination.unlink(missing_ok=True)
                    except OSError:
                        restored = False
                recovery = output / ".spx-stack-snapshot.json"
                # Stack runner retains its snapshot if rollback did not complete.
                rollback_ok = not recovery.exists() or json.loads(
                    recovery.read_text(encoding="utf-8")
                ).get("rolled_back", False)
                with file_lock(self.root / "sessions.lock"):
                    session = self._read(session_id)
                    session.update(
                        status=(
                            "FAILED"
                            if restored and rollback_ok
                            else "RECOVERY_REQUIRED"
                        ),
                        stage="rollback",
                        diagnostic=(
                            "Installation failed; previous generated files restored. See sanitized job diagnostics. Run SPX Setup to retry."
                            if restored and rollback_ok
                            else "Rollback requires inspection; previous configuration backup was retained. Do not start another installation."
                        ),
                    )
                    self._write(session)

    def _execute_stack(self, session, output):
        env = clean_environment()
        approved = session["plan"]["preflight"]
        env["SPX_SETUP_APPROVED_STACK"] = json.dumps(
            {
                "containers": sorted(
                    [c["id"], c["name"], c["image"], c["state"]]
                    for stack in approved["existing"]
                    for c in stack["containers"]
                ),
                "ports": sorted({p["host_port"] for p in approved["port_options"]}),
            }
        )
        env["SPX_SETUP_JOURNAL"] = str(
            self._directory(session["session_id"])
            / f"backup-{session['job']['job_id']}"
            / "changes.json"
        )
        env["SPX_BASE_URL"] = _endpoints(Path(session["plan"]["_stage"]))["api"]
        if os.name == "nt":
            command = [
                sys.executable,
                str(output / "stack_runner.py"),
                "start",
                "--yes",
            ]
        else:
            command = ["bash", str(output / "spx-start.sh"), "--yes"]
            env["SPX_SYSTEM_PYTHON_BIN"] = sys.executable
        key = self._key(session)
        from .stack_manager import redact

        lines = []
        process = subprocess.Popen(
            command,
            cwd=output,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in process.stdout:
            safe = redact(
                line.replace(key, "<redacted>").replace(
                    key.replace("-", ""), "<redacted>"
                )
            )
            lines.append(safe.rstrip())
            atomic_json(
                self._directory(session["session_id"]) / "progress.json",
                {"last_message": safe.rstrip(), "tail": lines[-30:]},
            )
        process.stdout.close()
        returncode = process.wait()
        text = "\n".join(lines)
        atomic_json(
            self._directory(session["session_id"]) / "diagnostics.json",
            {"exit_code": returncode, "output": text},
        )
        if returncode:
            raise SetupError("Stack installation failed", "INSTALL_FAILED")
        if "MCP configuration could not be refreshed" in text:
            with file_lock(self.root / "sessions.lock"):
                current = self._read(session["session_id"])
                current["mcp_warning"] = (
                    "Stack is healthy. Run SPX MCP Setup and reconnect MCP in your agent."
                )
                self._write(current)


def clean_environment():
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("SPX_"):
            env.pop(name)
    for name in (
        "SPX_PRODUCT_KEY",
        "SPX_BASE_URL",
        "PYTHON_BIN",
        "SPX_INSTALLER_PYTHON_BIN",
        "SSLKEYLOGFILE",
        "SPX_SETUP_JOURNAL",
    ):
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _pid_alive(pid):
    if os.name == "nt":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _source_digest(session):
    root = Path(session["source_root"])
    directories = [root / "installer", root / "library", root / "profiles"]
    directories += [
        Path(session[name]) for name in ("catalog", "profiles") if session[name]
    ]
    files = sorted(
        {
            p
            for d in directories
            for p in d.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
    )
    project = root / "pyproject.toml"
    return _digest(
        [(str(p), hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
        + [
            (
                "pyproject",
                hashlib.sha256(
                    project.read_bytes() if project.exists() else b""
                ).hexdigest(),
            )
        ]
    )


def _suggest_port(start, unavailable):
    return next((port for port in range(start, 65536) if port not in unavailable), None)


def _port_options(compose):
    from .modbus_port_configurator import _binding_parts

    return [
        {
            "key": f"{name}:{parts[2]}/{parts[3].lstrip('/') or 'tcp'}",
            "service": name,
            "host_port": parts[1],
            "container_port": parts[2],
            "transport": parts[3].lstrip("/") or "tcp",
        }
        for name, service in compose.get("services", {}).items()
        for binding in service.get("ports", [])
        if (parts := _binding_parts(binding)) is not None
    ]


def _map_ports(directory, mappings):
    if not isinstance(mappings, dict) or any(
        type(p) is not int or not 1 <= p <= 65535 for p in mappings.values()
    ):
        raise SetupError(
            "port_mappings must map port option keys to host ports 1–65535"
        )
    if not mappings:
        return
    from .modbus_port_configurator import _binding_parts

    compose_file = directory / "docker-compose.generated.yml"
    compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    valid = {p["key"] for p in _port_options(compose)}
    if set(mappings) - valid:
        raise SetupError(
            "Unknown port mapping; use the port_options returned by setup_plan"
        )
    # Modbus range and gateway must move as a unit through the existing mapper.
    modbus_range = [
        p
        for p in _port_options(compose)
        if p["service"] == "spx-server" and 5020 <= p["container_port"] <= 5120
    ]
    changed_range = [p for p in modbus_range if p["key"] in mappings]
    if changed_range and (
        len(changed_range) != len(modbus_range)
        or len({mappings[p["key"]] - p["container_port"] for p in changed_range}) != 1
    ):
        raise SetupError(
            "Map the complete Modbus 5020–5120 range with one consistent offset"
        )
    for name in ("docker-compose.generated.yml", "docker-compose.transaction.yml"):
        file = directory / name
        payload = yaml.safe_load(file.read_text(encoding="utf-8"))
        for service_name, service in payload["services"].items():
            base_name = re.sub(r"^transaction-__TRANSACTION_TOKEN__-", "", service_name)
            ports = []
            for binding in service.get("ports", []):
                parts = _binding_parts(binding)
                if parts:
                    bind, host, container, transport = parts
                    host = mappings.get(
                        f"{base_name}:{container}/{transport.lstrip('/') or 'tcp'}",
                        host,
                    )
                    binding = f"{bind}{host}:{container}{transport}"
                ports.append(binding)
            service["ports"] = ports
        file.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    bundle_file = directory / "bundle.json"
    bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
    for record in bundle.get("service_port_mappings", []):
        key = f"{record['compose_service']}:{record['container_port']}/{record.get('transport') or 'tcp'}"
        if key in mappings:
            record["host_port"] = mappings[key]
    settings = bundle.get("modbus_port_mappings")
    if settings:
        settings["gateway_host_port"] = mappings.get(
            "spx-server:502/tcp", settings["gateway_host_port"]
        )
        offset = mappings.get("spx-server:5020/tcp", 5020) - 5020
        settings["instance_host_port_start"] += offset
        settings["instance_host_port_end"] += offset
    atomic_json(bundle_file, bundle)


def _validate_ports(directory):
    compose = yaml.safe_load(
        (directory / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )
    from .modbus_port_configurator import _binding_parts

    used = []
    for name, service in compose["services"].items():
        for binding in service.get("ports", []):
            parts = _binding_parts(binding)
            if parts is None:
                raise SetupError("Unsupported host port binding")
            prefix, host, container, suffix = parts
            protocol = suffix.lstrip("/") or "tcp"
            address = prefix.rstrip(":") or "0.0.0.0"
            if not 1 <= host <= 65535:
                raise SetupError("Invalid host port")
            for prior in used:
                if prior[1:3] == (host, protocol) and (
                    address == prior[0] or "0.0.0.0" in {address, prior[0]}
                ):
                    if prior[3:] != (name, container):
                        raise SetupError(
                            "Selected services have conflicting host port mappings"
                        )
            used.append((address, host, protocol, name, container))


def _endpoints(directory):
    compose = yaml.safe_load(
        (directory / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )
    options = {p["key"]: p["host_port"] for p in _port_options(compose)}
    return {
        "api": f"http://127.0.0.1:{options.get('spx-server:8000/tcp', 8000)}",
        "ui": (
            f"http://localhost:{options['spx-ui:3000/tcp']}"
            if "spx-ui:3000/tcp" in options
            else None
        ),
    }
