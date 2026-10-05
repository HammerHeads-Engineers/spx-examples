"""Regressions from the first conversation-led Windows installation."""

import json
from pathlib import Path
import sys
import threading
import time

import pytest

from installer.setup_session import SetupEngine, SetupError, atomic_json

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def draft(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "active", KEY, initial={"start": False})
    return engine, session


@pytest.mark.parametrize(
    "name",
    [
        "assets/homeassistant/config/home-assistant.log",
        "assets/homeassistant/config/home-assistant.log.1",
        "assets/homeassistant/config/.storage/core.restore_state",
        "assets/homeassistant/config/home-assistant_v2.db-wal",
        "assets/matter/data/chip.json",
    ],
)
def test_runtime_writes_do_not_invalidate_approved_plan(draft, name):
    engine, session = draft
    file = Path(session["output"]) / name
    file.parent.mkdir(parents=True)
    file.write_text("before")
    plan = engine.plan(session["session_id"])
    file.write_text("after")
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    assert job["plan_id"] == plan["plan_id"]


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "docker-compose.generated.yml",
        "assets/homeassistant/config/configuration.yaml",
    ],
)
def test_real_configuration_edits_still_invalidate_plan(draft, name):
    engine, session = draft
    file = Path(session["output"]) / name
    file.parent.mkdir(parents=True)
    file.write_text("before")
    plan = engine.plan(session["session_id"])
    file.write_text("after")
    with pytest.raises(SetupError, match="conditions changed"):
        engine.apply(
            session["session_id"], plan["plan_id"], plan["revision"], launch=False
        )


def test_community_limit_checked_before_generation_or_docker(tmp_path, monkeypatch):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(
        tmp_path / "active", "CO" + "A" * 28, initial={"start": False}
    )
    public = engine.get(session["session_id"])
    assert public["license"]["plan"] == "Community"
    assert public["license"]["instance_limit"] == 5
    assert "CO" + "A" * 28 not in json.dumps(public)
    index = engine._index(engine._read(session["session_id"]))
    model = next(iter(index.models))
    engine.update(
        session["session_id"],
        {
            "model_ids": [model],
            "instances": [
                {"model_id": model, "instance_key": str(i)} for i in range(6)
            ],
        },
    )
    monkeypatch.setattr(
        engine, "_preflight", lambda *a: pytest.fail("Over-limit plan reached Docker")
    )
    with pytest.raises(SetupError) as error:
        engine.plan(session["session_id"])
    assert error.value.code == "LICENSE_INSTANCE_LIMIT"
    assert error.value.details == {"requested": 6, "limit": 5}
    assert not Path(session["output"]).exists()


def test_default_plan_contains_catalog_but_zero_instances(draft):
    engine, session = draft
    engine.update(
        session["session_id"],
        {
            "packages": list(
                engine._index(engine._read(session["session_id"])).industries
            )
        },
    )
    plan = engine.plan(session["session_id"])
    assert plan["selection"]["model_ids"]
    assert plan["selection"]["instances"] == []
    assert plan["selection"]["start_instances"] == []


def test_compact_status_waits_for_lifecycle_change_without_returning_catalog(draft):
    engine, session = draft
    engine.plan(session["session_id"])
    before = engine.status(session["session_id"], compact=True)
    assert "plan" not in before and "selection" not in before

    def change():
        time.sleep(0.1)
        current = engine._read(session["session_id"])
        current.update(status="SUCCEEDED", stage="complete")
        engine._write(current)

    writer = threading.Thread(target=change)
    writer.start()
    result = engine.status(
        session["session_id"],
        after_cursor=before["cursor"],
        wait_seconds=2,
        compact=True,
    )
    writer.join(2)
    assert result["status"] == "SUCCEEDED" and result["changed"]
    assert result["cursor"] != before["cursor"]
    assert KEY not in json.dumps(result)


def test_status_times_out_and_log_chatter_does_not_change_cursor(draft):
    engine, session = draft
    before = engine.status(session["session_id"], compact=True)
    atomic_json(
        engine._directory(session["session_id"]) / "progress.json",
        {"last_message": "another model", "stage": "installing"},
    )
    event = engine.status(session["session_id"], compact=True)
    atomic_json(
        engine._directory(session["session_id"]) / "progress.json",
        {"last_message": "next model", "stage": "installing"},
    )
    result = engine.status(
        session["session_id"],
        after_cursor=event["cursor"],
        wait_seconds=0.1,
        compact=True,
    )
    assert not result["changed"]
    assert result["cursor"] == event["cursor"] != before["cursor"]
    assert result["progress"]["last_message"] == "next model"


@pytest.mark.parametrize("timeout", [-1, 31, float("inf"), float("nan")])
def test_status_rejects_unbounded_waits(draft, timeout):
    engine, session = draft
    with pytest.raises(SetupError):
        engine.status(session["session_id"], wait_seconds=timeout)


def test_agent_guidance_is_english_and_uses_minimal_defaults(draft, tmp_path):
    from installer.setup_workspace import prepare_workspace

    engine, session = draft
    root = prepare_workspace(
        tmp_path / "workspace",
        engine,
        session["session_id"],
        python=Path(sys.executable),
        bootstrap=False,
    )
    guide = (root / "AGENTS.md").read_text(encoding="utf-8")
    install = (root / "INSTALLATION.md").read_text(encoding="utf-8")
    assert "Complete SPX setup and installation" in install
    assert install.isascii()
    assert "zero instances" in guide
    assert "one approval" in guide
    assert "after_cursor" in guide
    assert "every few seconds" not in guide


def test_port_suggestion_moves_entire_range_and_avoids_collisions():
    from installer.setup_session import suggest_port_mappings

    options = [
        {
            "key": f"spx-server:{p}/tcp",
            "service": "spx-server",
            "host_port": p,
            "container_port": p,
            "transport": "tcp",
        }
        for p in range(5020, 5121)
    ]
    options += [
        {
            "key": "spx-ui:3000/tcp",
            "service": "spx-ui",
            "host_port": 3000,
            "container_port": 3000,
            "transport": "tcp",
        }
    ]
    unavailable = {3000, 3001, 5040, 5130} | set(range(5020, 5121))
    mapping = suggest_port_mappings(options, {3000, 5040}, unavailable)
    assert len(mapping) == 102
    assert len({mapping[p["key"]] - p["container_port"] for p in options[:-1]}) == 1
    assert not set(mapping.values()) & unavailable
    assert len(set(mapping.values())) == 102


def test_compact_options_preserve_no_start_no_ui_and_omit_model_enumeration(draft):
    engine, session = draft
    engine.update(session["session_id"], {"install_spx_ui": False})
    options = engine.options(session["session_id"], compact=True)
    assert "models" not in options and "profiles" not in options
    recommended = options["recommended_selection"]
    assert not recommended["install_spx_ui"] and not recommended["start"]
    assert not recommended["install_instances"] and recommended["instances"] == []
    assert recommended["service_ids"] == []
    engine.update(session["session_id"], recommended)
    plan = engine.plan(session["session_id"])
    assert plan["selection"]["model_ids"] and plan["selection"]["service_ids"] == []


@pytest.mark.parametrize(
    "prefix,limit,expected", [("CO", 5, 5), ("CO", 9, 5), ("PR", 12, 12), ("PR", 0, 0)]
)
def test_license_summary_checks_embedded_fields_without_personal_data(
    prefix, limit, expected
):
    import binascii
    from installer.product_key import product_key_summary

    # Format fixture with invalid dates: never usable for a licensed installation.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    payload = (
        "".join(f"{alphabet.index(c):05b}" for c in prefix) + f"{limit:08b}" + "0" * 100
    )
    checksum = binascii.crc_hqx(int(payload + "00", 2).to_bytes(15, "big"), 0xFFFF)
    bits = payload + f"{checksum:016b}" + "0" * 16
    key = "".join(alphabet[int(bits[i : i + 5], 2)] for i in range(0, 150, 5))
    summary = product_key_summary(key)
    assert summary["instance_limit"] == expected
    assert summary["source"] == "embedded_fields" and not summary["server_verified"]
    assert set(summary) == {"plan", "instance_limit", "source", "server_verified"}
    assert key not in json.dumps(summary)


def test_status_cli_wait_and_compact_output(draft, capsys):
    from installer.cli import main

    engine, session = draft
    cursor = engine.status(session["session_id"], compact=True)["cursor"]
    assert (
        main(
            [
                "setup",
                "--state-root",
                str(engine.root),
                "status",
                "--session-id",
                session["session_id"],
                "--compact",
                "--after-cursor",
                cursor,
                "--wait-seconds",
                "0.1",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert not result["changed"] and result["cursor"] == cursor
    assert "selection" not in result


def test_status_wait_does_not_hold_session_lock(draft):
    engine, session = draft
    before = engine.status(session["session_id"], compact=True)
    result = {}
    waiter = threading.Thread(
        target=lambda: result.update(
            engine.status(
                session["session_id"],
                after_cursor=before["cursor"],
                wait_seconds=2,
                compact=True,
            )
        )
    )
    waiter.start()
    changed = engine.update(session["session_id"], {"install_spx_ui": False})
    waiter.join(2)
    assert not waiter.is_alive()
    assert result["revision"] == changed["revision"] and result["changed"]


def test_preflight_port_patch_is_applicable_without_handwritten_range(
    draft, monkeypatch
):
    from installer.stack_manager import PreflightResult

    engine, session = draft
    engine.update(
        session["session_id"],
        {
            "packages": list(
                engine._index(engine._read(session["session_id"])).industries
            ),
            "start": True,
            "service_ids": None,
        },
    )

    def inspect(manager, ports, **kwargs):
        return PreflightResult(
            occupied_ports={5040: ["Windows service CDPSvc"]},
            required_ports=ports,
            required_tcp_ports=kwargs["required_tcp_ports"],
        )

    monkeypatch.setattr("installer.setup_session.StackManager.preflight", inspect)
    blocked = engine.plan(session["session_id"])
    assert not blocked["ready"] and blocked["errors"][0]["code"] == "PORT_CONFLICT"
    patch = blocked["preflight"]["suggested_port_mappings"]
    assert len(patch) == 101
    engine.update(session["session_id"], {"port_mappings": patch})
    ready = engine.plan(session["session_id"])
    assert ready["ready"] and not ready["preflight"]["conflicts"]


def test_worker_groups_actual_bootstrap_output_into_catalog_phase(draft, monkeypatch):
    import io

    engine, session = draft
    engine.plan(session["session_id"])
    private = engine._read(session["session_id"])
    private["job"] = {"job_id": "phase-test"}

    class Process:
        stdout = io.StringIO(
            "[bootstrap] Importing catalog\n  - Registered model sensor via HTTP\n"
        )

        def wait(self):
            return 0

    monkeypatch.setattr(
        "installer.setup_session.subprocess.Popen", lambda *a, **kw: Process()
    )
    engine._execute_stack(private, Path(session["output"]))
    assert (
        engine.status(session["session_id"], compact=True)["progress"]["stage"]
        == "catalog"
    )
