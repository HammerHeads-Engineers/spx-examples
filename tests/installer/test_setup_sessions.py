"""Setup must plan without touching the active installation or leaking keys."""

import json
from pathlib import Path

import pytest

from installer.setup_session import SetupEngine, SetupError

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def engine(tmp_path):
    return SetupEngine(tmp_path / "private")


def draft(engine, tmp_path):
    session = engine.create(tmp_path / "generated", KEY)
    return engine.update(
        session["session_id"],
        {"protocols": ["http"], "install_instances": False, "start": False},
    )


def test_key_is_private_and_update_does_not_touch_active(engine, tmp_path):
    output = tmp_path / "generated"
    output.mkdir()
    (output / ".env").write_text("previous")
    session = draft(engine, tmp_path)
    plan = engine.plan(session["session_id"])
    assert (output / ".env").read_text() == "previous"
    assert KEY not in json.dumps(plan)
    assert KEY not in json.dumps(engine.get(session["session_id"]))


def test_selection_change_invalidates_plan(engine, tmp_path):
    session = draft(engine, tmp_path)
    plan = engine.plan(session["session_id"])
    engine.update(session["session_id"], {"install_spx_ui": False})
    with pytest.raises(SetupError, match="plan"):
        engine.apply(session["session_id"], plan["plan_id"], plan["revision"])


def test_secret_arguments_and_unknown_options_rejected(engine, tmp_path):
    session = draft(engine, tmp_path)
    for selection in ({"license_key": KEY}, {"product_key": KEY}, {"typo": True}):
        with pytest.raises(SetupError):
            engine.update(session["session_id"], selection)


def test_snapshot_data_survives_generation(engine, tmp_path):
    session = draft(engine, tmp_path)
    output = tmp_path / "generated"
    (output / "data/snapshots").mkdir(parents=True)
    snapshot = output / "data/snapshots/user.json"
    snapshot.write_text("user data")
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    assert engine.get(session["session_id"])["status"] == "SUCCEEDED"
    assert snapshot.read_text() == "user data"
    assert (output / "bundle.json").exists()


def test_invalid_session_id_cannot_escape_state_root(engine):
    with pytest.raises(SetupError):
        engine.get("../../elsewhere")


def test_failed_start_restores_files_and_removes_new_artifacts(
    engine, tmp_path, monkeypatch
):
    output = tmp_path / "generated"
    output.mkdir()
    (output / ".env").write_text("old key configuration")
    session = draft(engine, tmp_path)
    # Preflight fixtures prove transaction behavior without touching real Docker.
    monkeypatch.setattr(
        engine,
        "_preflight",
        lambda *a: {
            "checked": True,
            "existing": [],
            "conflicts": [],
            "port_options": [],
            "errors": [],
        },
    )
    engine.update(session["session_id"], {"start": True})
    plan = engine.plan(session["session_id"])

    def fail(*a):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(engine, "_execute_stack", fail)
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    assert engine.get(session["session_id"])["status"] == "FAILED"
    assert (output / ".env").read_text() == "old key configuration"
    assert not (output / "bundle.json").exists()


def test_apply_retry_is_idempotent_and_blocks_other_sessions(engine, tmp_path):
    first = draft(engine, tmp_path)
    plan = engine.plan(first["session_id"])
    job = engine.apply(
        first["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    assert (
        engine.apply(
            first["session_id"], plan["plan_id"], plan["revision"], launch=False
        )
        == job
    )
    second = engine.create(tmp_path / "other", KEY, initial={"start": False})
    other_plan = engine.plan(second["session_id"])
    with pytest.raises(SetupError, match="Another"):
        engine.apply(
            second["session_id"],
            other_plan["plan_id"],
            other_plan["revision"],
            launch=False,
        )


def test_active_configuration_change_requires_new_plan(engine, tmp_path):
    session = draft(engine, tmp_path)
    plan = engine.plan(session["session_id"])
    output = tmp_path / "generated"
    output.mkdir()
    (output / ".env").write_text("changed outside Setup")
    with pytest.raises(SetupError, match="conditions changed"):
        engine.apply(
            session["session_id"], plan["plan_id"], plan["revision"], launch=False
        )


def test_endpoint_remapping_survives_existing_port_configurator(engine, tmp_path):
    from installer.modbus_port_configurator import _ports_from_compose
    import yaml

    session = draft(engine, tmp_path)
    engine.update(
        session["session_id"],
        {"port_mappings": {"spx-server:8000/tcp": 18000, "spx-ui:3000/tcp": 13000}},
    )
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    output = tmp_path / "generated"
    compose = yaml.safe_load((output / "docker-compose.generated.yml").read_text())
    assert 18000 in _ports_from_compose(compose)
    assert 13000 in _ports_from_compose(compose)
    assert (
        engine.get(session["session_id"])["endpoints"]["api"]
        == "http://127.0.0.1:18000"
    )
    assert "SPX_BASE_URL=http://127.0.0.1:18000" in (output / ".env").read_text()


def test_port_mapping_validation_does_not_wait_until_docker(engine, tmp_path):
    session = draft(engine, tmp_path)
    engine.update(
        session["session_id"], {"port_mappings": {"spx-server:8000/tcp": 3000}}
    )
    with pytest.raises(SetupError, match="port"):
        engine.plan(session["session_id"])


def test_failed_worker_does_not_report_success(engine, tmp_path, monkeypatch):
    session = draft(engine, tmp_path)
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    current = engine._read(session["session_id"])
    current["job"]["pid"] = 99999
    engine._write(current)
    monkeypatch.setattr("installer.setup_session._pid_alive", lambda _: False)
    assert engine.get(session["session_id"])["status"] == "RECOVERY_REQUIRED"


def test_cli_exposes_errors_as_json(engine, tmp_path, capsys):
    from installer.cli import main

    assert (
        main(
            [
                "setup",
                "--state-root",
                str(engine.root),
                "status",
                "--session-id",
                "bad",
                "--json",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_mounts_and_old_api_are_restored_before_container_restart(tmp_path):
    from installer.deployment_journal import restore_files

    output, backup = tmp_path / "active", tmp_path / "backup"
    for root in (output, backup):
        (root / "library").mkdir(parents=True)
    for name in (
        ".env",
        "startup-models.json",
        "library/model.yaml",
        "stack_manager.py",
    ):
        (output / name).write_text("candidate")
        (backup / name).write_text("previous")
    journal = backup / "changes.json"
    journal.write_text(
        json.dumps(
            {
                "output": str(output),
                "backup": str(backup),
                "previous_api_url": "http://127.0.0.1:18000",
                "files": [
                    {"path": name, "existed": True}
                    for name in (
                        ".env",
                        "startup-models.json",
                        "library/model.yaml",
                        "stack_manager.py",
                    )
                ],
            }
        )
    )
    assert restore_files(journal, mounts_only=True) == "http://127.0.0.1:18000"
    assert (output / ".env").read_text() == "previous"
    assert (output / "library/model.yaml").read_text() == "previous"
    assert (output / "stack_manager.py").read_text() == "candidate"


def test_udp_mapping_keeps_binding_and_transport(engine, tmp_path):
    import yaml

    session = engine.create(
        tmp_path / "active",
        KEY,
        initial={
            "protocols": ["bacnet"],
            "start": False,
            "port_mappings": {"spx-server:47808/udp": 47900},
        },
    )
    plan = engine.plan(session["session_id"])
    directory = Path(engine._read(session["session_id"])["plan"]["_stage"])
    compose = yaml.safe_load((directory / "docker-compose.generated.yml").read_text())
    assert any(
        str(binding).endswith("47900:47808/udp")
        for binding in compose["services"]["spx-server"]["ports"]
    )


def test_stack_change_and_replacement_rejection_never_modify_active(
    engine, tmp_path, monkeypatch
):
    session = draft(engine, tmp_path)
    engine.update(session["session_id"], {"start": True})
    preflight = {
        "checked": True,
        "existing": [],
        "conflicts": [],
        "port_options": [],
        "errors": [],
    }
    monkeypatch.setattr(engine, "_preflight", lambda *a: preflight)
    plan = engine.plan(session["session_id"])
    preflight["existing"] = [{"project": "old", "containers": []}]
    with pytest.raises(SetupError, match="conditions changed"):
        engine.apply(
            session["session_id"], plan["plan_id"], plan["revision"], launch=False
        )
    replacement = engine.plan(session["session_id"])
    assert not replacement["ready"]
    assert replacement["errors"][0]["code"] == "REPLACEMENT_REQUIRED"
    assert not (tmp_path / "generated").exists()


def test_new_revision_after_success_can_apply_and_clears_old_diagnostics(
    engine, tmp_path
):
    from installer.setup_session import atomic_json

    session = draft(engine, tmp_path)
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    atomic_json(
        engine._directory(session["session_id"]) / "diagnostics.json", {"old": True}
    )
    changed = engine.update(session["session_id"], {"install_spx_ui": False})
    assert "diagnostics" not in changed and "endpoints" not in changed
    plan = engine.plan(session["session_id"])
    new_job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    assert new_job["job_id"] != job["job_id"]
    engine.run_job(session["session_id"], new_job["job_id"])
    assert engine.get(session["session_id"])["status"] == "SUCCEEDED"


def test_retained_rollback_snapshot_blocks_new_plan(engine, tmp_path):
    session = draft(engine, tmp_path)
    output = tmp_path / "generated"
    output.mkdir()
    (output / ".spx-stack-snapshot.json").write_text('{"rolled_back":false}')
    plan = engine.plan(session["session_id"])
    assert not plan["ready"]
    assert plan["errors"][0]["code"] == "RECOVERY_REQUIRED"
