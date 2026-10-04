# SPDX-License-Identifier: MIT
"""Start or stop an installer-generated SPX stack."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from typing import Any, Sequence


class StartFailure(Exception):
    def __init__(self, stage: str, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code or 1


def _redact(message: str) -> str:
    message = re.sub(
        r"(?i)(spx[_-]?product[_-]?key\s*[=:]\s*)[^\s,;]+",
        r"\1<redacted>",
        message,
    )
    return re.sub(r"(?i)(--product-key\s+)[^\s]+", r"\1<redacted>", message)


def _run(args: Sequence[str], *, cwd: Path, stage: str) -> None:
    try:
        result = subprocess.run(list(args), cwd=str(cwd), check=False)
    except OSError as exc:
        raise StartFailure(stage, str(exc)) from exc
    if result.returncode:
        raise StartFailure(
            stage,
            f"{Path(args[0]).name} exited with code {result.returncode}",
            result.returncode,
        )


def _read_bundle(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            bundle = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StartFailure(
            "runtime", f"Could not read bundle configuration: {exc}"
        ) from exc
    if not isinstance(bundle, dict):
        raise StartFailure("runtime", "Bundle configuration must be a JSON object")
    return bundle


def _manager_command(
    manager: Path,
    command: str,
    *,
    compose_file: Path,
    env_file: Path,
    installation_id: str,
    snapshot: Path | None = None,
    ports: str | None = None,
    tcp_ports: str | None = None,
    api_url: str | None = None,
    final_names: list[str] | None = None,
    transaction_token: str | None = None,
    diagnostics_path: Path | None = None,
    failure_stage: str | None = None,
) -> list[str]:
    args = [
        sys.executable,
        str(manager),
        command,
        "--compose-file",
        str(compose_file),
        "--env-file",
        str(env_file),
        "--project",
        "spx",
        "--installation-id",
        installation_id,
    ]
    if snapshot is not None:
        args.extend(["--snapshot", str(snapshot)])
    if ports is not None:
        args.extend(["--ports", ports])
    if tcp_ports is not None:
        args.extend(["--tcp-ports", tcp_ports])
    if api_url is not None:
        args.extend(["--api-url", api_url])
    if transaction_token:
        args.extend(["--transaction-token", transaction_token])
    if diagnostics_path is not None:
        args.extend(["--diagnostics-path", str(diagnostics_path)])
    if failure_stage:
        args.extend(["--failure-stage", failure_stage])
    for mapping in final_names or []:
        args.extend(["--final-name", mapping])
    return args


def _stop(script_dir: Path) -> int:
    try:
        bundle = _read_bundle(script_dir / "bundle.json")
    except StartFailure as exc:
        print(f"[spx-stop] stage={exc.stage}: {_redact(str(exc))}", file=sys.stderr)
        return exc.exit_code
    installation_id = str(bundle.get("installation_id") or "")
    if not installation_id:
        print(
            "[spx-stop] stage=runtime: Bundle configuration is missing its installation ID.",
            file=sys.stderr,
        )
        return 1
    manager = script_dir / "stack_manager.py"
    compose_file = script_dir / "docker-compose.generated.yml"
    env_file = script_dir / ".env"
    if not manager.is_file() or not compose_file.is_file():
        print(
            "[spx-stop] Generated stack files are incomplete. Run SPX Setup again.",
            file=sys.stderr,
        )
        return 1
    try:
        _run(
            _manager_command(
                manager,
                "stop",
                compose_file=compose_file,
                env_file=env_file,
                installation_id=installation_id,
            ),
            cwd=script_dir,
            stage="stop",
        )
    except StartFailure as exc:
        print(f"[spx-stop] stage={exc.stage}: {_redact(str(exc))}", file=sys.stderr)
        return exc.exit_code
    print("[spx-stop] SPX stack stopped.")
    return 0


def _start(script_dir: Path, *, assume_yes: bool) -> int:
    stage = "runtime"
    transaction_compose: Path | None = None
    transaction_prepared = False
    staged_ports_file: Path | None = None
    diagnostics_path: Path | None = None
    token = ""
    api_url = os.environ.get("SPX_BASE_URL") or "http://127.0.0.1:8000"
    runtime_python = sys.executable
    manager = script_dir / "stack_manager.py"
    compose_file = script_dir / "docker-compose.generated.yml"
    env_file = script_dir / ".env"
    snapshot = script_dir / ".spx-stack-snapshot.json"
    bundle_path = script_dir / "bundle.json"
    transaction_template = script_dir / "docker-compose.transaction.yml"
    bundle: dict[str, Any] = {}

    try:
        if not shutil.which("docker"):
            raise StartFailure(
                stage,
                "Docker CLI was not found. Install Docker Desktop with Compose, then run SPX Setup again.",
            )
        for required in (
            manager,
            compose_file,
            env_file,
            bundle_path,
            transaction_template,
            script_dir / "network.py",
            script_dir / "modbus_port_configurator.py",
            script_dir / "runtime_bootstrap.py",
            script_dir / "bootstrap_runner.py",
            script_dir / "product_key.py",
        ):
            if not required.is_file():
                raise StartFailure(
                    stage, f"Required generated file is missing: {required.name}"
                )

        bundle = _read_bundle(bundle_path)
        installation_id = str(bundle.get("installation_id") or "")
        if not installation_id:
            raise StartFailure(
                stage, "Bundle configuration is missing its installation ID"
            )
        _run(
            [
                runtime_python,
                str(script_dir / "product_key.py"),
                "--env-file",
                str(env_file),
            ],
            cwd=script_dir,
            stage="product-key",
        )
        requirement = str(bundle.get("spx_python_requirement") or "spx-python")
        bootstrap = script_dir / "runtime_bootstrap.py"
        print("[spx-start] Preparing the isolated SPX runtime...")
        bootstrap_environment = os.environ.copy()
        bootstrap_environment.pop("SSLKEYLOGFILE", None)
        bootstrap_environment["PYTHONIOENCODING"] = "utf-8"
        try:
            runtime_result = subprocess.run(
                [
                    runtime_python,
                    str(bootstrap),
                    "--venv-dir",
                    str(script_dir / ".spx-runtime"),
                    "--package",
                    "requests",
                    "--package",
                    requirement,
                    "--package",
                    "pyyaml",
                ],
                cwd=str(script_dir),
                env=bootstrap_environment,
                stdout=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise StartFailure(
                stage, f"Could not prepare the local Python runtime: {exc}"
            ) from exc
        if runtime_result.returncode:
            raise StartFailure(
                stage,
                f"Python runtime bootstrap exited with code {runtime_result.returncode}",
                runtime_result.returncode,
            )
        runtime_python = runtime_result.stdout.decode("utf-8", errors="replace").strip()
        if not runtime_python or not Path(runtime_python).is_file():
            raise StartFailure(
                stage, "Python runtime bootstrap did not return a valid interpreter"
            )

        token = uuid.uuid4().hex
        diagnostics_path = script_dir / "logs" / f"start-{token}.json"
        transaction_compose = script_dir / f".docker-compose.transaction.{token}.yml"
        transaction_service = f"transaction-{token}-spx-ui"
        staged_ports_file = script_dir / f".spx-modbus-ports.pending.{token}.json"

        services = bundle.get("services", [])
        if (
            isinstance(services, list)
            and "btvirt_adapter" in services
            and os.name == "nt"
        ):
            print(
                "[spx-start] BLE/GATT service 'btvirt_adapter' is not supported on Windows. "
                "Use WSL2, macOS/Linux, or an external BLE bridge.",
                file=sys.stderr,
            )

        stage = "preflight"
        _run(
            [
                runtime_python,
                str(script_dir / "modbus_port_configurator.py"),
                "stage",
                "--compose-file",
                str(compose_file),
                "--bundle",
                str(bundle_path),
                "--env-file",
                str(env_file),
                "--staged-file",
                str(staged_ports_file),
            ],
            cwd=script_dir,
            stage=stage,
        )
        port_result = subprocess.run(
            [
                runtime_python,
                str(script_dir / "modbus_port_configurator.py"),
                "required-ports",
                "--staged-file",
                str(staged_ports_file),
            ],
            cwd=str(script_dir),
            stdout=subprocess.PIPE,
            check=False,
        )
        if port_result.returncode:
            raise StartFailure(
                stage,
                "Could not read the staged Modbus port configuration",
                port_result.returncode,
            )
        ports = port_result.stdout.decode("utf-8", errors="replace").strip()
        tcp_port_result = subprocess.run(
            [
                runtime_python,
                str(script_dir / "modbus_port_configurator.py"),
                "required-tcp-ports",
                "--staged-file",
                str(staged_ports_file),
            ],
            cwd=str(script_dir),
            stdout=subprocess.PIPE,
            check=False,
        )
        if tcp_port_result.returncode:
            raise StartFailure(
                stage,
                "Could not read the staged TCP port mappings",
                tcp_port_result.returncode,
            )
        tcp_ports = tcp_port_result.stdout.decode("utf-8", errors="replace").strip()
        _run(
            [
                runtime_python,
                str(script_dir / "network.py"),
                "--env-file",
                str(env_file),
                "--published-ports",
                ports,
            ],
            cwd=script_dir,
            stage=stage,
        )
        prepare = _manager_command(
            manager,
            "prepare",
            compose_file=compose_file,
            env_file=env_file,
            installation_id=installation_id,
            snapshot=snapshot,
            ports=ports,
            tcp_ports=tcp_ports,
        )
        if assume_yes:
            prepare.append("--yes")
        _run(prepare, cwd=script_dir, stage=stage)
        transaction_prepared = True
        _run(
            [
                runtime_python,
                str(script_dir / "modbus_port_configurator.py"),
                "commit",
                "--compose-file",
                str(compose_file),
                "--transaction-template",
                str(transaction_template),
                "--bundle",
                str(bundle_path),
                "--staged-file",
                str(staged_ports_file),
            ],
            cwd=script_dir,
            stage=stage,
        )
        staged_ports_file.unlink(missing_ok=True)
        staged_ports_file = None
        template = transaction_template.read_text(encoding="utf-8")
        transaction_compose.write_text(
            template.replace("__TRANSACTION_TOKEN__", token),
            encoding="utf-8",
        )
        bundle = _read_bundle(bundle_path)

        stage = "compose"
        _run(
            [
                "docker",
                "compose",
                "-p",
                "spx",
                "-f",
                str(transaction_compose),
                "--env-file",
                str(env_file),
                "up",
                "-d",
            ],
            cwd=script_dir,
            stage=stage,
        )

        stage = "healthcheck"
        _run(
            _manager_command(
                manager,
                "wait-health",
                compose_file=compose_file,
                env_file=env_file,
                installation_id=installation_id,
                api_url=api_url,
                transaction_token=token,
                diagnostics_path=diagnostics_path,
            ),
            cwd=script_dir,
            stage=stage,
        )

        if bundle.get("ui_enabled"):
            stage = "ui"
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    "spx",
                    "-f",
                    str(transaction_compose),
                    "--env-file",
                    str(env_file),
                    "ps",
                    "--services",
                    "--status",
                    "running",
                ],
                cwd=str(script_dir),
                stdout=subprocess.PIPE,
                check=False,
            )
            if result.returncode:
                raise StartFailure(
                    stage,
                    f"Docker Compose exited with code {result.returncode}",
                    result.returncode,
                )
            running_services = result.stdout.decode(
                "utf-8", errors="replace"
            ).splitlines()
            if transaction_service not in running_services:
                raise StartFailure(stage, "SPX UI is not running")

        stage = "bootstrap"
        _run(
            [
                runtime_python,
                str(script_dir / "bootstrap_runner.py"),
                "--bundle",
                str(bundle_path),
                "--api-url",
                api_url,
            ],
            cwd=script_dir,
            stage=stage,
        )

        stage = "start"
        try:
            status_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    "spx",
                    "-f",
                    str(transaction_compose),
                    "--env-file",
                    str(env_file),
                    "ps",
                    "--services",
                    "--status",
                    "running",
                ],
                cwd=str(script_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise StartFailure(
                stage, f"Could not inspect running services: {exc}"
            ) from exc
        if status_result.returncode:
            raise StartFailure(
                stage,
                f"Docker Compose exited with code {status_result.returncode}",
                status_result.returncode,
            )
        running_services = status_result.stdout.decode(
            "utf-8", errors="replace"
        ).splitlines()
        if not running_services:
            raise StartFailure(stage, "No selected SPX services are running")
        normalized_services = [
            re.sub(r"^transaction-[^-]+-", "", service.strip())
            for service in running_services
            if service.strip()
        ]
        print(f"[spx-start] Running services: {', '.join(normalized_services)}")

        stage = "commit"
        final_names = bundle.get("final_container_names", [])
        if not isinstance(final_names, list):
            final_names = []
        _run(
            _manager_command(
                manager,
                "commit",
                compose_file=compose_file,
                env_file=env_file,
                installation_id=installation_id,
                snapshot=snapshot,
                final_names=[str(mapping) for mapping in final_names],
                transaction_token=token,
            ),
            cwd=script_dir,
            stage=stage,
        )
        try:
            transaction_compose.unlink(missing_ok=True)
        except OSError:
            pass
        transaction_compose = None
        try:
            try:
                from installer.mcp_workspace import synchronize_managed_workspace
            except ImportError:
                from mcp_workspace import synchronize_managed_workspace
            if synchronize_managed_workspace(env_file):
                print('[spx-start] Managed MCP configuration refreshed. Reconnect MCP in Codex.')
        except Exception:
            # The stack is already committed and healthy. MCP setup failure
            # must not roll it back or disclose configuration/secret values.
            print('[spx-start] SPX stack is healthy; MCP configuration could not be refreshed. '
                  'Run SPX MCP Setup, then reconnect MCP in Codex.', file=sys.stderr)
        print()
        print("[spx-start] SPX started successfully.")
        print(
            "[spx-start] UI: http://localhost:3000 (if enabled), API: http://localhost:8000"
        )
        try:
            subprocess.run(
                [
                    runtime_python,
                    str(script_dir / "modbus_port_configurator.py"),
                    "summary",
                    "--bundle",
                    str(bundle_path),
                    "--compose-file",
                    str(compose_file),
                ],
                cwd=str(script_dir),
                check=False,
            )
        except OSError:
            pass
        return 0
    except StartFailure as exc:
        stage = exc.stage
        message = str(exc)
        exit_code = exc.exit_code
    except OSError as exc:
        message = str(exc)
        exit_code = 1

    rollback_note = "; attempting rollback" if transaction_prepared else ""
    print(
        f"[spx-start] stage={stage}: {_redact(message)}{rollback_note}", file=sys.stderr
    )
    if transaction_prepared:
        installation_id = str(bundle.get("installation_id") or "")
        try:
            _run(
                _manager_command(
                    manager,
                    "diagnose",
                    compose_file=compose_file,
                    env_file=env_file,
                    installation_id=installation_id,
                    transaction_token=token,
                    diagnostics_path=diagnostics_path,
                    failure_stage=stage,
                ),
                cwd=script_dir,
                stage="diagnostics",
            )
        except (StartFailure, OSError):
            print("[spx-start] Could not save failure diagnostics.", file=sys.stderr)
        try:
            _run(
                _manager_command(
                    manager,
                    "rollback",
                    compose_file=compose_file,
                    env_file=env_file,
                    installation_id=installation_id,
                    snapshot=snapshot,
                    transaction_token=token,
                    api_url=api_url,
                ),
                cwd=script_dir,
                stage="rollback",
            )
        except (StartFailure, OSError):
            print(
                "[spx-start] stage=rollback: automatic restore was not completed",
                file=sys.stderr,
            )
            print(
                f"[spx-start] Recovery snapshot retained: {snapshot}", file=sys.stderr
            )
            print(
                "[spx-start] Run SPX Setup from the SPX application / Start menu; inspect the saved diagnostics before retrying.",
                file=sys.stderr,
            )
            # Keep the candidate configuration for recovery after partial rollback.
            transaction_compose = None
        if diagnostics_path is not None:
            print(
                f"[spx-start] Failure diagnostics: {diagnostics_path}", file=sys.stderr
            )
    if transaction_compose is not None:
        try:
            transaction_compose.unlink(missing_ok=True)
        except OSError:
            pass
    if staged_ports_file is not None:
        try:
            staged_ports_file.unlink(missing_ok=True)
        except OSError:
            pass
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start or stop the generated SPX stack"
    )
    parser.add_argument(
        "command", nargs="?", choices=("start", "stop"), default="start"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept replacement of the detected SPX stack",
    )
    args = parser.parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    if args.command == "stop":
        return _stop(script_dir)
    return _start(script_dir, assume_yes=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
