# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from installer.stack_manager import (
    LABEL_INSTALLATION_ID,
    LABEL_MANAGED_BY,
    LABEL_STACK,
    StackManager,
    UserDeclined,
)


def completed(argv: list[str], stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def test_preflight_detects_labelled_stack_and_ignores_unrelated_container(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    labelled = {
        "Id": "old-id",
        "Name": "/spx-server",
        "Config": {
            "Image": "simplephysx/spx-server:v1.0.0-rc.64",
            "Labels": {
                LABEL_STACK: "true",
                LABEL_MANAGED_BY: "installer",
                "com.simplephysx.spx.project": "spx",
                LABEL_INSTALLATION_ID: "old-installation",
                "com.docker.compose.project": "spx",
                "com.docker.compose.project.config_files": "/tmp/old-compose.yml",
                "com.docker.compose.service": "spx-server",
            },
        },
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
        "NetworkSettings": {"Ports": {"8000/tcp": [{"HostPort": "8000"}]}},
    }
    unrelated = {
        "Id": "other-id",
        "Name": "/unrelated-db",
        "Config": {"Image": "postgres:16", "Labels": {"com.docker.compose.project": "other"}},
        "State": {"Status": "running"},
        "NetworkSettings": {"Ports": {"8000/tcp": [{"HostPort": "8000"}]}},
    }

    def runner(argv, **kwargs):  # noqa: ANN001
        calls.append(list(argv))
        if argv[:3] == ["docker", "ps", "-aq"]:
            return completed(list(argv), "old-id\nother-id\n")
        if argv[:2] == ["docker", "inspect"]:
            return completed(list(argv), json.dumps([labelled if argv[2] == "old-id" else unrelated]))
        return completed(list(argv))

    manager = StackManager(
        tmp_path / "compose.yml",
        runner=runner,
        platform="linux",
    )
    result = manager.preflight([8000])

    assert len(result.active_stacks) == 1
    assert result.active_stacks[0].project == "spx"
    assert result.active_stacks[0].ports == [8000]
    assert result.conflicts == {8000: ["container spx-server", "container unrelated-db"]}
    assert not any(
        len(call) > 2 and call[0:2] in (["docker", "stop"], ["docker", "rename"]) and "other-id" in call
        for call in calls
    )


def test_prepare_decline_does_not_stop_or_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = StackManager(tmp_path / "compose.yml", runner=lambda argv, **kwargs: completed(list(argv)))
    existing = type("Existing", (), {})()
    existing.containers = [type("Container", (), {"name": "spx-server", "image": "image", "health": "healthy", "ports": [8000], "running": True})()]
    existing.project = "spx"
    existing.compose_files = []
    existing.ports = [8000]
    existing.source = "labels"
    existing.active = True
    fake_result = type(
        "Result",
        (),
        {
            "existing": [existing],
            "active_stacks": [existing],
            "conflicts": {},
            "unrelated_conflicts": {},
        },
    )()
    monkeypatch.setattr(manager, "preflight", lambda ports: fake_result)
    commands: list[list[str]] = []
    monkeypatch.setattr(manager, "snapshot_existing", lambda stack, path: commands.append(["snapshot"]))

    with pytest.raises(UserDeclined):
        manager.prepare(tmp_path / "snapshot.json", input_fn=lambda prompt: "n")

    assert commands == []


def test_docker_desktop_proxy_is_not_an_unrelated_port_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = StackManager(tmp_path / "compose.yml", runner=lambda argv, **kwargs: completed(list(argv)))
    container = type("Container", (), {"ports": [8000], "name": "spx-server", "id": "server-id"})()
    monkeypatch.setattr(manager, "list_containers", lambda: [container])
    monkeypatch.setattr(manager, "_fallback_host_ports", lambda: {8000: ["host process"], 8080: ["host process"]})

    occupied = manager.occupied_ports()

    assert occupied[8000] == ["container spx-server"]
    assert occupied[8080] == ["host process"]


def test_prepare_snapshots_only_detected_ids_and_never_removes_data(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    manager = StackManager(tmp_path / "compose.yml", runner=lambda argv, **kwargs: (calls.append(list(argv)) or completed(list(argv))))
    old = type("Container", (), {"id": "old-id", "name": "spx-server", "running": True})()
    stack = type("Stack", (), {"containers": [old]})()
    snapshot = manager.snapshot_existing(stack, tmp_path / "snapshot.json")

    assert snapshot.containers[0]["id"] == "old-id"
    assert [call[1] for call in calls if len(call) > 1 and call[1] in {"stop", "rename"}] == ["stop", "rename"]
    assert not any(call[1] in {"rm", "volume", "image"} for call in calls if len(call) > 1)
    assert any(call[:4] == ["docker", "update", "--label-rm", "com.docker.compose.project"] for call in calls)


def test_rollback_stops_current_transaction_and_restores_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    manager = StackManager(
        tmp_path / "compose.yml",
        installation_id="new-installation",
        runner=lambda argv, **kwargs: (calls.append(list(argv)) or completed(list(argv))),
    )
    current = type("Container", (), {"id": "new-id", "name": "spx-server", "running": True})()
    monkeypatch.setattr(manager, "transaction_containers", lambda: [current])
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "project": "spx",
                "installation_id": "new-installation",
                "containers": [{"id": "old-id", "name": "spx-server", "rollback_name": "spx-rollback-old"}],
                "created_at": 0,
            }
        ),
        encoding="utf-8",
    )

    manager.rollback(snapshot_path)

    assert [call[1:3] for call in calls if call[1] in {"stop", "rename", "start"}] == [
        ["stop", "new-id"],
        ["rename", "new-id"],
        ["rename", "old-id"],
        ["start", "old-id"],
    ]
    assert not any("rm" in call or "volume" in call or "image" in call for call in calls)
