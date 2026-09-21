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
    ContainerInfo,
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


def test_same_compose_project_does_not_make_unrelated_image_managed(
    tmp_path: Path,
) -> None:
    manager = StackManager(tmp_path / "compose.yml", runner=lambda argv, **kwargs: completed(list(argv)))
    unrelated = ContainerInfo(
        id="other-id",
        name="spx-postgres",
        image="postgres:16",
        labels={"com.docker.compose.project": "spx"},
        state="running",
    )

    assert not manager.is_managed_container(unrelated)


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
    assert snapshot.containers[0]["name"] == "spx-server"
    assert snapshot.containers[0]["snapshot_name"] == "spx-snapshot-old-id"
    assert [call[1] for call in calls if len(call) > 1 and call[1] in {"stop", "rename"}] == ["stop", "rename"]
    assert not any(call[1] in {"volume", "image"} for call in calls if len(call) > 1)
    assert any(call[:4] == ["docker", "update", "--label-rm", "com.docker.compose.project"] for call in calls)


def test_commit_removes_only_snapshot_containers_and_keeps_data_resources(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    manager = StackManager(
        tmp_path / "compose.yml",
        runner=lambda argv, **kwargs: (calls.append(list(argv)) or completed(list(argv))),
    )
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "project": "spx",
                "installation_id": "new-installation",
                "containers": [
                    {"id": "old-id", "name": "spx-server", "snapshot_name": "spx-snapshot-old"}
                ],
                "created_at": 0,
            }
        ),
        encoding="utf-8",
    )

    manager.commit(snapshot_path)

    assert not snapshot_path.exists()
    assert [call[1:3] for call in calls if len(call) > 2 and call[1] == "stop"] == [
        ["stop", "old-id"],
    ]
    assert [call[1:4] for call in calls if len(call) > 3 and call[1] == "rm"] == [
        ["rm", "-f", "old-id"],
    ]
    assert not any("-v" in call for call in calls)


def test_commit_assigns_stable_names_to_transaction_containers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    manager = StackManager(
        tmp_path / "compose.yml",
        installation_id="new-installation",
        runner=lambda argv, **kwargs: (calls.append(list(argv)) or completed(list(argv))),
    )
    transaction = ContainerInfo(
        id="new-id",
        name="spx-transaction-new-spx-server",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        labels={"com.docker.compose.service": "spx-server"},
        state="running",
    )
    monkeypatch.setattr(manager, "transaction_containers", lambda: [transaction])
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "project": "spx",
                "installation_id": "new-installation",
                "containers": [],
                "created_at": 0,
            }
        ),
        encoding="utf-8",
    )

    manager.commit(snapshot_path, {"spx-server": "spx-server"})

    assert [call[1:4] for call in calls if call[1] == "rename"] == [
        ["rename", "new-id", "spx-server"]
    ]


def test_transaction_containers_excludes_snapshots_with_same_installation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = StackManager(
        tmp_path / "compose.yml",
        installation_id="same-installation",
        runner=lambda argv, **kwargs: completed(list(argv)),
    )
    transaction = ContainerInfo(
        id="new-id",
        name="spx-transaction-run-spx-server",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        labels={LABEL_INSTALLATION_ID: "same-installation"},
        state="running",
    )
    snapshot = ContainerInfo(
        id="old-id",
        name="spx-snapshot-old-id",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        labels={LABEL_INSTALLATION_ID: "same-installation"},
        state="running",
    )
    monkeypatch.setattr(manager, "list_containers", lambda: [transaction, snapshot])

    assert manager.transaction_containers() == [transaction]


def test_stop_stack_stops_stable_names_but_not_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    manager = StackManager(
        tmp_path / "compose.yml",
        installation_id="same-installation",
        runner=lambda argv, **kwargs: (calls.append(list(argv)) or completed(list(argv))),
    )
    stable = ContainerInfo(
        id="stable-id",
        name="spx-server",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        labels={LABEL_INSTALLATION_ID: "same-installation"},
        state="running",
    )
    snapshot = ContainerInfo(
        id="snapshot-id",
        name="spx-snapshot-old-id",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        labels={LABEL_INSTALLATION_ID: "same-installation"},
        state="running",
    )
    monkeypatch.setattr(manager, "list_containers", lambda: [stable, snapshot])

    manager.stop_stack()

    assert [call[1:3] for call in calls if call[1] == "stop"] == [["stop", "stable-id"]]


def test_legacy_rollback_named_container_is_detected_only_for_known_spx_image(
    tmp_path: Path,
) -> None:
    manager = StackManager(tmp_path / "compose.yml", runner=lambda argv, **kwargs: completed(list(argv)))
    managed = ContainerInfo(
        id="old-id",
        name="spx-rollback-old-id",
        image="simplephysx/spx-server:v1.0.0-rc.64",
        state="running",
    )
    unrelated = ContainerInfo(
        id="other-id",
        name="spx-rollback-other",
        image="postgres:16",
        state="running",
    )

    assert manager.is_managed_container(managed)
    assert not manager.is_managed_container(unrelated)


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
    assert [call[1:4] for call in calls if call[1] == "rm"] == [["rm", "-f", "new-id"]]
    assert not any("volume" in call or "image" in call for call in calls)
    assert not any("-v" in call for call in calls)
