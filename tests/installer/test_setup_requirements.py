"""Regressions from installing the entire catalog before discovering KNX needs."""

import json
from pathlib import Path

import pytest
import yaml

from installer.setup_session import SetupEngine, SetupError

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def agent(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "active", KEY, initial={"start": False})
    private = engine._read(session["session_id"])
    private["requirements_required"] = True
    engine._write(private)
    return engine, session["session_id"]


def requirements(protocol="knx", **changes):
    value = {
        "description": "Test building devices over " + protocol,
        "catalog_scope": "selected",
        "protocols": [protocol],
        "required_services": [],
        "external_services": {},
        "remove_services": [],
        "unresolved": [],
        "decisions": {
            "install_spx_ui": True,
            "start": False,
            "service_bind_addresses": {},
            "port_mappings": {},
            "replace_existing": False,
        },
    }
    value.update(changes)
    return value


def configure(agent, protocol="knx", **changes):
    engine, sid = agent
    return engine.update(
        sid,
        {"protocols": [protocol], "requirements": requirements(protocol), **changes},
    )


def test_agent_cannot_plan_without_describing_needs(agent, monkeypatch):
    engine, sid = agent
    monkeypatch.setattr(
        engine,
        "_preflight",
        lambda *a: pytest.fail("Incomplete requirements reached Docker"),
    )
    plan = engine.plan(sid)
    assert not plan["ready"]
    assert plan["errors"][0]["code"] == "REQUIREMENTS_INCOMPLETE"
    assert not Path(engine.get(sid)["output"]).exists()
    with pytest.raises(SetupError):
        engine.apply(sid, plan["plan_id"], plan["revision"], launch=False)


def test_recommended_draft_does_not_choose_entire_catalog(agent):
    engine, sid = agent
    options = engine.options(sid, compact=True)
    assert options["recommended_selection"]["packages"] == []
    assert options["recommended_selection"]["service_ids"] is None
    assert options["requirements_schema"]["catalog_scope"] == [
        "selected",
        "full_catalog",
        "base",
    ]


@pytest.mark.parametrize(
    "protocol,service", [("knx", "knx_gateway"), ("mqtt", "mqtt_broker")]
)
def test_required_gateway_is_resolved_without_creating_instances(
    agent, protocol, service
):
    engine, sid = agent
    configure(agent, protocol)
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    assert service in plan["selection"]["service_ids"]
    assert plan["selection"]["instances"] == plan["selection"]["start_instances"] == []
    compose = yaml.safe_load(
        (
            Path(
                plan["_stage"]
                if "_stage" in plan
                else engine._read(sid)["plan"]["_stage"]
            )
            / "docker-compose.generated.yml"
        ).read_text()
    )
    assert service in compose["services"]
    assert plan["requirements"]["description"]
    assert KEY not in json.dumps(plan)


def test_missing_required_service_blocks_plan(agent):
    engine, sid = agent
    configure(agent, service_ids=[])
    plan = engine.plan(sid)
    assert not plan["ready"]
    assert any(
        e["code"] == "MISSING_REQUIRED_SERVICE" and e["service_id"] == "knx_gateway"
        for e in plan["errors"]
    )


@pytest.mark.parametrize("change", ["unresolved", "decisions"])
def test_unanswered_setup_decisions_block_plan(agent, change):
    engine, sid = agent
    req = requirements()
    if change == "unresolved":
        req["unresolved"] = ["Local gateway or existing KNX router?"]
    else:
        req["decisions"].pop("start")
    configure(agent, requirements=req)
    assert not engine.plan(sid)["ready"]


def test_changed_choices_require_updated_decision_record(agent):
    engine, sid = agent
    configure(agent)
    plan = engine.plan(sid)
    engine.update(sid, {"install_spx_ui": False})
    blocked = engine.plan(sid)
    assert not blocked["ready"]
    with pytest.raises(SetupError):
        engine.apply(sid, plan["plan_id"], plan["revision"], launch=False)


def test_external_mqtt_is_explicit_and_does_not_install_local_broker(agent):
    engine, sid = agent
    req = requirements(
        "mqtt",
        external_services={
            "mqtt_broker": {
                "endpoint": "mqtt://192.0.2.10:1883",
                "provisioning": "Set mqtt_broker_host and mqtt_broker_port when creating instances",
            }
        },
    )
    configure(agent, "mqtt", requirements=req)
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    assert "mqtt_broker" not in plan["selection"]["service_ids"]
    assert plan["external_services"]["mqtt_broker"]["verified"] is False
    assert (
        "mqtt_broker_host" in plan["external_services"]["mqtt_broker"]["provisioning"]
    )


@pytest.mark.parametrize(
    "endpoint",
    ["mqtt://user:secret@example.com:1883", "not an endpoint", "http://example.com"],
)
def test_external_endpoint_cannot_hide_credentials_or_wrong_transport(agent, endpoint):
    req = requirements(
        "mqtt",
        external_services={
            "mqtt_broker": {
                "endpoint": endpoint,
                "provisioning": "Configure runtime inputs",
            }
        },
    )
    with pytest.raises(SetupError):
        configure(agent, "mqtt", requirements=req)


def test_full_catalog_requires_explicit_scope_and_preserves_zero_instances(agent):
    engine, sid = agent
    options = engine.options(sid, compact=True)
    configure(
        agent,
        packages=[p["id"] for p in options["packages"]],
        requirements=requirements(catalog_scope="full_catalog"),
    )
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    assert len(plan["selection"]["model_ids"]) > 50
    assert plan["selection"]["service_ids"] == ["knx_gateway"]


def test_base_installation_is_a_deliberate_choice(agent):
    engine, sid = agent
    engine.update(
        sid,
        {
            "requirements": requirements(catalog_scope="base", protocols=[]),
            "model_ids": [],
            "service_ids": [],
        },
    )
    plan = engine.plan(sid)
    assert plan["ready"] and not plan["selection"]["model_ids"]


def test_update_preserves_services_until_removal_is_explicit(agent):
    engine, sid = agent
    output = Path(engine.get(sid)["output"])
    output.mkdir()
    (output / "bundle.json").write_text(
        json.dumps({"models": [], "services": ["mqtt_broker"], "ui_enabled": True})
    )
    installed = engine.options(sid, compact=True)["installed_selection"]
    assert installed["service_ids"] == ["mqtt_broker"]
    configure(agent)
    blocked = engine.plan(sid)
    assert any(e["code"] == "SERVICE_REMOVAL_UNCONFIRMED" for e in blocked["errors"])
    configure(agent, service_ids=["mqtt_broker", "knx_gateway"])
    assert engine.plan(sid)["ready"]
    configure(
        agent,
        service_ids=None,
        requirements=requirements(remove_services=["mqtt_broker"]),
    )
    plan = engine.plan(sid)
    assert plan["ready"] and plan["changes"]["removed_services"] == ["mqtt_broker"]


def test_transitive_dependencies_are_installed(agent):
    engine, sid = agent
    engine.update(
        sid,
        {
            "model_ids": [],
            "requirements": requirements(
                catalog_scope="base", protocols=[], required_services=["matter_server"]
            ),
        },
    )
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    assert set(plan["selection"]["service_ids"]) >= {
        "matter_server",
        "homeassistant_bridge",
        "knx_gateway",
    }


def test_legacy_explicit_selection_does_not_require_conversation(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(
        tmp_path / "active", KEY, initial={"protocols": ["knx"], "start": False}
    )
    assert engine.plan(session["session_id"])["ready"]


def test_handoff_marks_requirements_mandatory_and_asks_needs_first(agent, tmp_path):
    from installer.setup_workspace import _write_instructions

    engine, sid = agent
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_instructions(workspace, Path("python"), engine.root, sid)
    guide = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "What would you like to use SPX for?" in guide
    assert "Never select the full catalog" in guide
    assert "external_services" in guide and "requirements" in guide
    assert guide.index("What would you like") < guide.index("setup_plan")


def test_full_catalog_cannot_be_silently_labelled_selected(agent):
    engine, sid = agent
    configure(
        agent, packages=[p["id"] for p in engine.options(sid, compact=True)["packages"]]
    )
    assert any(
        e["code"] == "CATALOG_SCOPE_MISMATCH" for e in engine.plan(sid)["errors"]
    )


def test_required_protocol_cannot_disappear_through_platform_pruning(
    agent, monkeypatch
):
    monkeypatch.setattr("installer.selection.platform.system", lambda: "Windows")
    engine, sid = agent
    configure(agent, "ble")
    plan = engine.plan(sid)
    assert not plan["ready"]
    assert any(e["code"] == "MISSING_REQUIRED_PROTOCOL" for e in plan["errors"])


def test_external_dependency_does_not_leave_invalid_compose_peer(agent):
    engine, sid = agent
    engine.update(
        sid,
        {
            "model_ids": [],
            "requirements": requirements(
                catalog_scope="base",
                protocols=[],
                required_services=["matter_server"],
                external_services={
                    "homeassistant_bridge": {
                        "endpoint": "http://192.0.2.20:8123",
                        "provisioning": "Connect existing Home Assistant to the Matter service",
                    }
                },
            ),
        },
    )
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    stage = Path(engine._read(sid)["plan"]["_stage"])
    compose = yaml.safe_load((stage / "docker-compose.generated.yml").read_text())
    assert "homeassistant_bridge" not in compose["services"]
    assert "knx_gateway" not in compose["services"]
    assert compose["services"]["matter_server"]["depends_on"] == []
    bundle = json.loads((stage / "bundle.json").read_text())
    assert set(bundle["required_compose_services"]) == set(compose["services"])
    assert bundle["external_services"]["homeassistant_bridge"]["verified"] is False


def test_installed_no_ui_and_explicit_draft_choices_survive_recommendation(agent):
    engine, sid = agent
    output = Path(engine.get(sid)["output"])
    output.mkdir()
    (output / "bundle.json").write_text(
        json.dumps({"models": [], "services": [], "ui_enabled": False})
    )
    assert (
        engine.options(sid, compact=True)["recommended_selection"]["install_spx_ui"]
        is False
    )
    engine.update(sid, {"install_spx_ui": True, "service_ids": ["knx_gateway"]})
    recommended = engine.options(sid, compact=True)["recommended_selection"]
    assert recommended["install_spx_ui"] is True
    assert recommended["service_ids"] == ["knx_gateway"]


def test_cli_adapter_cannot_bypass_requirements_or_echo_external_credentials(agent):
    from installer.setup_cli import invoke

    engine, sid = agent
    assert not invoke(engine, "plan", sid)["result"]["ready"]
    result = invoke(
        engine,
        "update-selection",
        sid,
        selection={
            "requirements": requirements(
                "mqtt",
                external_services={
                    "mqtt_broker": {
                        "endpoint": "mqtt://user:sensitive-value@example.com:1883",
                        "provisioning": "Configure endpoint",
                    }
                },
            ),
        },
    )
    assert not result["ok"] and result["error"]["code"] == "INVALID_REQUIREMENTS"
    assert "sensitive-value" not in json.dumps(result)


def test_agent_can_query_only_models_for_required_protocol(agent):
    engine, sid = agent
    options = engine.options(sid, compact=False, protocols=["knx"])
    assert options["models"] and all(
        "knx" in model["protocols"] for model in options["models"]
    )
    assert len(options["models"]) < engine.options(sid, compact=True)["model_count"]
    assert all("services" in model for model in options["models"])
    with pytest.raises(SetupError):
        engine.options(sid, protocols=["unknown"])


def test_protocol_filters_narrow_a_chosen_pack_in_agent_mode(agent):
    engine, sid = agent
    configure(agent, packages=["smart_building_pack"])
    plan = engine.plan(sid)
    assert plan["ready"], plan["errors"]
    index = engine._index(engine._read(sid))
    assert all(
        "knx" in index.models[mid].protocols for mid in plan["selection"]["model_ids"]
    )
    assert plan["selection"]["service_ids"] == ["knx_gateway"]
