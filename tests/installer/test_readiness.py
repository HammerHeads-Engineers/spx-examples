# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from http.client import BadStatusLine
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

from installer import stack_manager as sm


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(sm.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        sm.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )
    return now


@pytest.fixture
def server():
    return sm.ContainerInfo(
        id="candidate",
        name="spx-transaction-current-spx-server",
        image="simplephysx/spx-server:v1.0.0-rc.67",
        state="running",
        status="running",
        health="healthy",
        labels={
            sm.LABEL_INSTALLATION_ID: "install",
            "com.docker.compose.project": "spx",
            "com.docker.compose.service": "transaction-current-spx-server",
        },
    )


@pytest.fixture
def manager(tmp_path):
    return sm.StackManager(
        tmp_path / "compose.yml", installation_id="install", transaction_token="current"
    )


def test_readiness_filters_installation_and_batches_inspection(
    manager, server, monkeypatch
):
    other = sm.ContainerInfo(
        id="stale",
        name="spx-transaction-stale-spx-server",
        image=server.image,
        labels={
            **server.labels,
            "com.docker.compose.service": "transaction-stale-spx-server",
        },
        state="running",
        health="healthy",
    )

    def inspect(item):
        return {
            "Id": item.id,
            "Name": item.name,
            "Config": {"Image": item.image, "Labels": item.labels},
            "State": {"Status": item.state, "Health": {"Status": item.health}},
        }

    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        output = (
            "candidate\nstale\n"
            if argv[1] == "ps"
            else json.dumps([inspect(server), inspect(other)])
        )
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(manager, "_runner", runner)
    assert manager._readiness_containers(sm.time.monotonic() + 10) == [server]
    assert len(calls) == 2
    assert f"label={sm.LABEL_INSTALLATION_ID}=install" in calls[0][0]
    assert calls[1][0] == ["docker", "inspect", "candidate", "stale"]
    assert all(0 < kw["timeout"] <= 5 for _, kw in calls)
    # Stable names assigned by a partially completed commit still belong to this transaction.
    server.name = "spx-server"
    other.labels = {
        **server.labels,
        "com.docker.compose.service": "transaction-stale-spx-server",
    }
    assert manager.transaction_containers() == [server]


def test_readiness_retries_host_api_until_ready(manager, server, clock, monkeypatch):
    monkeypatch.setattr(manager, "_readiness_containers", lambda deadline: [server])
    api = Mock(
        side_effect=[
            {"ready": False, "status": 503, "error": "HTTP 503"},
            {"ready": True, "status": 200},
        ]
    )
    monkeypatch.setattr(manager, "_probe_api", api)
    manager.wait_health(timeout=5)
    assert api.call_count == 2 and clock[0] == 2
    assert manager.last_readiness["ready"] is True


@pytest.mark.parametrize(
    "cause", ["missing", "unhealthy", "paused", "refused", "http503", "docker_error"]
)
def test_timeout_reports_the_actual_condition(
    manager, server, clock, monkeypatch, capsys, cause
):
    if cause == "unhealthy":
        server.health = "unhealthy"
    if cause == "paused":
        server.state = "paused"
    reader = Mock(return_value=[] if cause == "missing" else [server])
    if cause == "docker_error":
        reader.side_effect = sm.StackManagerError("Docker inspect timed out")
    monkeypatch.setattr(manager, "_readiness_containers", reader)
    reason = "HTTP 503" if cause == "http503" else "Connection refused"
    api = Mock(return_value={"ready": False, "error": reason})
    monkeypatch.setattr(manager, "_probe_api", api)
    expected = {
        "missing": "found 0",
        "unhealthy": "unhealthy",
        "paused": "state=paused",
        "refused": "Connection refused",
        "http503": "HTTP 503",
        "docker_error": "Docker inspect timed out",
    }[cause]
    with pytest.raises(sm.StackManagerError, match=expected):
        manager.wait_health(timeout=3)
    assert expected in capsys.readouterr().out
    assert (
        api.call_count == 0
        if cause in {"missing", "unhealthy", "paused", "docker_error"}
        else api.call_count > 0
    )


def test_success_after_deadline_is_not_accepted(manager, server, clock, monkeypatch):
    monkeypatch.setattr(manager, "_readiness_containers", lambda deadline: [server])

    def slow_api(*args):
        clock[0] = 10
        return {"ready": True, "status": 200}

    monkeypatch.setattr(manager, "_probe_api", slow_api)
    with pytest.raises(sm.StackManagerError):
        manager.wait_health(timeout=3)


def test_docker_command_timeout_is_reported(manager, monkeypatch):
    runner = Mock(side_effect=subprocess.TimeoutExpired(["docker", "inspect"], 2))
    monkeypatch.setattr(manager, "_runner", runner)
    with pytest.raises(sm.StackManagerError, match="timed out"):
        manager.docker(["inspect", "candidate"], timeout=2)
    assert runner.call_args.kwargs["timeout"] == 2


@pytest.mark.parametrize(
    "url,local",
    [
        ("http://127.0.0.1:8000", True),
        ("http://localhost:8000", True),
        ("http://[::1]:8000", True),
        ("http://configured-host:8000", False),
    ],
)
def test_api_probe_bypasses_proxy_only_on_loopback(manager, monkeypatch, url, local):
    response = Mock()
    response.status = 200
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    build = Mock(return_value=opener)
    external = Mock(return_value=response)
    monkeypatch.setattr(sm.urllib.request, "build_opener", build)
    monkeypatch.setattr(sm.urllib.request, "urlopen", external)
    assert manager._probe_api(url)["ready"] is True
    assert build.called == local and external.called != local


@pytest.mark.parametrize(
    "error,expected",
    [
        (
            urllib.error.HTTPError(
                "http://remote/health", 503, "unavailable", {}, None
            ),
            "HTTP 503",
        ),
        (urllib.error.URLError(ConnectionRefusedError("refused")), "refused"),
        (BadStatusLine("malformed HTTP status"), "malformed HTTP status"),
    ],
)
def test_api_probe_preserves_error_detail(manager, monkeypatch, error, expected):
    monkeypatch.setattr(sm.urllib.request, "urlopen", Mock(side_effect=error))
    result = manager._probe_api("http://remote:8000")
    assert result["ready"] is False and expected in result["error"]


def test_diagnostics_are_retained_and_redact_dotenv_secrets(
    tmp_path, server, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text(
        "SPX_PRODUCT_KEY=private-test-key\nSERVICE_PASSWORD=private-password\n"
    )
    manager = sm.StackManager(tmp_path / "compose.yml", env, installation_id="install")
    monkeypatch.setattr(manager, "_readiness_containers", lambda deadline: [server])
    manager.last_readiness = {
        "api": {"url": "http://user:password@host", "error": "private-test-key"}
    }
    monkeypatch.setattr(
        manager,
        "docker",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [],
            0,
            "private-test-key private-password Authorization: Bearer private-bearer\nSPX_PRODUCT_KEY=another-key\n",
            "",
        ),
    )
    path = tmp_path / "logs" / "failure.json"
    manager.capture_diagnostics(path, "healthcheck")
    content = path.read_text()
    for secret in (
        "private-test-key",
        "private-password",
        "private-bearer",
        "user:password",
        "another-key",
    ):
        assert secret not in content
    assert json.loads(content)["containers"][0]["id"] == "candidate"
    manager.last_readiness = {}
    manager.capture_diagnostics(path, "bootstrap")
    assert json.loads(path.read_text())["readiness"]["api"]["error"] == "<redacted>"


@pytest.mark.parametrize("operation", ["rename", "start"])
def test_partial_rollback_raises_and_keeps_snapshot(
    manager, tmp_path, monkeypatch, operation
):
    snapshot = tmp_path / "snapshot.json"
    sm.StackSnapshot(
        project="spx",
        installation_id="install",
        containers=[{"id": "old", "name": "spx-server"}],
        created_at=0,
    ).save(snapshot)
    monkeypatch.setattr(manager, "transaction_containers", lambda: [])
    monkeypatch.setattr(
        manager,
        "_runner",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1 if argv[1] == operation else 0, "", ""
        ),
    )
    with pytest.raises(sm.StackManagerError, match="Rollback incomplete"):
        manager.rollback(snapshot)
    assert snapshot.exists()


def test_rollback_requires_host_api_before_discarding_snapshot(
    manager, tmp_path, server, clock, monkeypatch
):
    snapshot = tmp_path / "snapshot.json"
    sm.StackSnapshot(
        project="spx",
        installation_id="install",
        containers=[{"id": "old", "name": "spx-server"}],
        created_at=0,
    ).save(snapshot)
    monkeypatch.setattr(manager, "transaction_containers", lambda: [])
    monkeypatch.setattr(
        manager,
        "_runner",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    monkeypatch.setattr(manager, "_inspect_ids", lambda ids, deadline: [server])
    monkeypatch.setattr(
        manager,
        "_probe_api",
        lambda *args: {"ready": False, "error": "Connection refused"},
    )
    with pytest.raises(
        sm.StackManagerError, match="Rollback not ready:.*Connection refused"
    ):
        manager.rollback(snapshot, timeout=3)
    assert snapshot.exists()


def test_docker_failure_reports_stderr_and_redacts_key(manager, clock, monkeypatch):
    monkeypatch.setenv("SPX_PRODUCT_KEY", "test-private-key")
    monkeypatch.setattr(
        manager,
        "_readiness_containers",
        Mock(
            side_effect=sm.CommandError(
                ["docker", "ps"], 1, "Docker daemon unavailable test-private-key"
            )
        ),
    )
    with pytest.raises(
        sm.StackManagerError, match="Docker daemon unavailable"
    ) as failure:
        manager.wait_health(timeout=2)
    assert "test-private-key" not in str(failure.value)


def test_empty_rollback_reports_no_previous_stack(
    manager, tmp_path, monkeypatch, capsys
):
    snapshot = tmp_path / "snapshot.json"
    sm.StackSnapshot.empty("spx", "install").save(snapshot)
    monkeypatch.setattr(manager, "transaction_containers", lambda: [])
    manager.rollback(snapshot)
    text = capsys.readouterr().out
    assert "no previous stack" in text and "SPX Setup" in text and not snapshot.exists()


def test_wait_health_cli_saves_failure_before_returning_error(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(
        sm.StackManager,
        "wait_health",
        lambda *args: (_ for _ in ()).throw(sm.StackManagerError("HTTP 503")),
    )
    monkeypatch.setattr(
        sm.StackManager,
        "capture_diagnostics",
        lambda *args: order.append("diagnostics"),
    )
    with pytest.raises(sm.StackManagerError, match="HTTP 503"):
        sm.main(
            [
                "wait-health",
                "--compose-file",
                str(tmp_path / "compose.yml"),
                "--diagnostics-path",
                str(tmp_path / "failure.json"),
            ]
        )
    assert order == ["diagnostics"]
