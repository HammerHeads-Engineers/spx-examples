"""Verify generated startup catalog, durable snapshots and host HTTP ports."""

import json

import yaml

from installer.generator import DeploymentGenerator
from installer.manifest import ManifestLoader
from installer.wizard import WizardSelection


def test_startup_manifest_is_secret_free_and_snapshots_survive_regeneration(tmp_path):
    index = ManifestLoader().load()
    selected = next(model.id for model in index.models.values() if "vision" in str(model.path))
    selection = WizardSelection(packages=[], profiles=[], protocols=["http"], install_examples=True,
                                install_spx_ui=True, offline_bundle=False, license_key="SECRET-TEST-KEY",
                                model_ids=[selected], service_ids=["http_gateway", "lwm2m_server"],
                                instances=[], start_instances=[])
    generator = DeploymentGenerator(index)
    generator.generate(selection, tmp_path)
    manifest = json.loads((tmp_path / "startup-models.json").read_text())
    assert manifest == {"models": [{"id": selected, "path": index.models[selected].path.as_posix()}]}
    assert "SECRET-TEST-KEY" not in (tmp_path / "startup-models.json").read_text()
    compose = yaml.safe_load((tmp_path / "docker-compose.generated.yml").read_text())
    server = compose["services"]["spx-server"]
    assert "--models-manifest" in server["command"]
    assert "./library:/app/library:ro" in server["volumes"]
    assert "./startup-models.json:/app/startup-models.json:ro" in server["volumes"]
    assert "./data/snapshots:/app/snapshots" in server["volumes"]
    assert any(port.endswith(":8093:8093") for port in server["ports"])
    snapshot = tmp_path / "data/snapshots/saved.json"
    snapshot.write_text('{"user": "configuration"}')
    generator.generate(selection, tmp_path)
    assert snapshot.read_text() == '{"user": "configuration"}'
    transaction = yaml.safe_load((tmp_path / "docker-compose.transaction.yml").read_text())
    assert "./data/snapshots:/app/snapshots" in next(service for service in transaction["services"].values() if service["image"] == server["image"])["volumes"]
    assert compose["services"]["lwm2m_server"]["environment"]["JAVA_TOOL_OPTIONS"] == "--add-opens=java.base/java.util=ALL-UNNAMED"
