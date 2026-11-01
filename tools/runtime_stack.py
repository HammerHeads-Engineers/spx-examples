"""Disposable Docker fixtures for model CI, never a product installation path."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import requests

from tools.model_catalog import CatalogError, ROOT, digest, json_bytes, verify_catalog
from tools.qualify_catalog import qualify_catalog
from tools.runtime_targets import PINNED_IMAGE, fixture_config


def redact_log(text: str, key: str) -> str:
    """Old server releases print decoded license identity as well as key data."""
    text = text.replace(key, "[REDACTED]") if key else text
    lines = []
    license_block = False
    for line in text.splitlines():
        lowered = line.lower()
        if "decoded product key info" in lowered:
            license_block = True
            lines.append("[REDACTED product license metadata]")
            continue
        if license_block:
            if lowered.startswith(
                ("loading from directory", "traceback", "error:", "fatal:")
            ):
                license_block = False
            else:
                continue
        if any(
            marker in lowered
            for marker in (
                "username:",
                "key created date:",
                "license expires date:",
                "plan name:",
            )
        ) or (lowered.startswith("user ") and " plan" in lowered):
            lines.append("[REDACTED product license metadata]")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


class RuntimeStack:
    def __init__(self, catalog: Path, image: str, logs: Path):
        if not PINNED_IMAGE.fullmatch(image):
            raise CatalogError(
                "Use a server image pinned by an immutable SHA-256 digest"
            )
        self.catalog = catalog.resolve()
        self.image = image
        self.logs = logs
        self.key = os.environ.get("SPX_PRODUCT_KEY", "")
        if not self.key:
            raise CatalogError(
                "Configure SPX_PRODUCT_KEY in the catalog-qualification environment"
            )
        self.prefix = "spx-model-ci-" + uuid.uuid4().hex[:12]
        self.network = self.prefix + "-net"
        self.containers = []
        self.created_network = False
        self.config = fixture_config()

    def docker(self, *args):
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode:
            # Docker output may include registry URLs; never echo secret-bearing arguments.
            raise CatalogError(
                "Docker fixture operation failed: "
                + result.stderr.replace(self.key, "[REDACTED]")[:1200]
            )
        return result.stdout.strip()

    def start(self, service, image, *arguments):
        name = self.prefix + "-" + service
        self.docker(
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            "spx.test-fixture=" + self.prefix,
            "--network",
            self.network,
            *arguments,
            image,
        )
        self.containers.append((service, name))
        return name

    def __enter__(self):
        try:
            self.docker(
                "network",
                "create",
                "--label",
                "spx.test-fixture=" + self.prefix,
                self.network,
            )
            self.created_network = True
            fixtures = ROOT / "tests/runtime"
            images = self.config["services"]
            self.start(
                "mqtt",
                images["mqtt"],
                "--network-alias",
                "mosquitto-server",
                "--mount",
                f"type=bind,source={fixtures / 'mosquitto.conf'},target=/mosquitto/config/mosquitto.conf,readonly",
            )
            # knxd requires a writable config; the source fixture stays read-only.
            name = self.prefix + "-knx"
            self.docker(
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "spx.test-fixture=" + self.prefix,
                "--network",
                self.network,
                "--network-alias",
                "knx_gateway",
                "--mount",
                f"type=bind,source={fixtures / 'knxd.ini'},target=/etc/qa.ini,readonly",
                "--entrypoint",
                "knxd",
                images["knx"],
                "/etc/qa.ini",
            )
            self.containers.append(("knx", name))
            self.start(
                "lwm2m",
                images["lwm2m"],
                "--network-alias",
                "leshan-server",
                "--network-alias",
                "leshan",
                "--hostname",
                "leshan",
                "--env",
                "JAVA_TOOL_OPTIONS=--add-opens=java.base/java.util=ALL-UNNAMED",
            )
            self.start(
                "matter",
                images["matter"],
                "--network-alias",
                "matter-server",
                "--mount",
                # Docker owns and removes this anonymous volume. A host bind
                # leaves root-owned Matter state that the CI runner cannot delete.
                "type=volume,target=/data",
            )
            server = self.prefix + "-server"
            self.docker(
                "run",
                "--detach",
                "--name",
                server,
                "--label",
                "spx.test-fixture=" + self.prefix,
                "--network",
                self.network,
                "--publish",
                "127.0.0.1::8000",
                "--add-host",
                "host.docker.internal:127.0.0.1",
                "--env",
                "SPX_PRODUCT_KEY",
                "--mount",
                f"type=bind,source={self.catalog / 'files/extensions'},target=/app/extensions,readonly",
                "--entrypoint",
                "sh",
                self.image,
                "-c",
                'exec python spx_server/main.py --address 0.0.0.0 --port 8000 --product-key "$SPX_PRODUCT_KEY" --extensions /app/extensions',
            )
            self.containers.append(("server", server))
            port = self.docker("port", server, "8000/tcp").rsplit(":", 1)[-1]
            if not port.isdecimal():
                raise CatalogError("Disposable API port was not published")
            self.url = "http://127.0.0.1:" + port
            for _ in range(90):
                state = self.docker("inspect", "--format", "{{.State.Status}}", server)
                if state in {"exited", "dead"}:
                    raise CatalogError(
                        "SPX server exited during startup; inspect the redacted server.log"
                    )
                try:
                    response = requests.get(
                        self.url + "/api/versions",
                        headers={"Authorization": "Bearer " + self.key},
                        timeout=2,
                    )
                    # An HTTP error still proves readiness; the qualifier records API incompatibility.
                    if response.status_code < 500:
                        return self
                except requests.RequestException:
                    pass
                time.sleep(1)
            raise CatalogError("Disposable SPX server did not become ready")
        except BaseException:
            self.close()
            raise

    def close(self):
        self.logs.mkdir(parents=True, exist_ok=True)
        errors = []
        for service, name in reversed(self.containers):
            result = subprocess.run(
                ["docker", "logs", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.logs.joinpath(service + ".log").write_text(
                redact_log(result.stdout + result.stderr, self.key),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["docker", "rm", "--force", "--volumes", name],
                capture_output=True,
                timeout=30,
            )
            if result.returncode:
                errors.append(service)
        self.containers.clear()
        if self.created_network:
            result = subprocess.run(
                ["docker", "network", "rm", self.network],
                capture_output=True,
                timeout=30,
            )
            if result.returncode:
                errors.append("network")
            self.created_network = False
        if errors:
            raise CatalogError(
                "Disposable infrastructure cleanup failed: " + ", ".join(errors)
            )

    def __exit__(self, *_):
        self.close()


def run_catalog(
    directory: Path, image: str, expected: str, output: Path, *, probe=False
):
    document = verify_catalog(directory)
    key = os.environ.get("SPX_PRODUCT_KEY", "")
    config = fixture_config()
    report = None
    client_output = io.StringIO()
    progress_stream = sys.stdout
    try:
        with RuntimeStack(
            directory, image, output.parent / (output.stem + "-logs")
        ) as stack:
            with redirect_stdout(client_output), redirect_stderr(client_output):
                report = qualify_catalog(
                    directory,
                    stack.url,
                    allow_writes=True,
                    expected_server=expected,
                    excluded_protocols=config["deferred_protocols"],
                    probe_all=probe,
                    progress=lambda index, total, name: print(
                        f"[{index}/{total}] {name}", file=progress_stream, flush=True
                    ),
                )
            report["environment"] = {
                "server_image": image,
                "service_images": config["services"],
                "kind": "disposable-docker",
            }
    except Exception as exc:
        if report is None:
            report = {
                "schema_version": 1,
                "status": "FAILED",
                "scope": "compatibility-probe" if probe else "full-catalog",
                "source_commit": document["source"]["commit"],
                "catalog_sha256": digest((directory / "catalog.json").read_bytes()),
                "server_version": None,
                "expected_server": expected,
                "results": [],
            }
        report["status"] = "FAILED"
        report["infrastructure_error"] = (
            (str(exc).replace(key, "[REDACTED]") if key else str(exc))
            if isinstance(exc, CatalogError)
            else type(exc).__name__
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    client_log = output.parent / (output.stem + "-logs") / "client.log"
    client_log.parent.mkdir(parents=True, exist_ok=True)
    client_log.write_text(redact_log(client_output.getvalue(), key), encoding="utf-8")
    output.write_bytes(json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--server-image", required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--probe-all", action="store_true")
    args = parser.parse_args()
    report = run_catalog(
        args.catalog,
        args.server_image,
        args.expected_server,
        args.output,
        probe=args.probe_all,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "server": args.expected_server,
                "scope": report["scope"],
                "tested": len(report["results"]),
                "excluded_models": report.get("excluded_models", []),
                "report": str(args.output),
            },
            indent=2,
        )
    )
    return int(report["status"] != "PASSED")


if __name__ == "__main__":
    raise SystemExit(main())
