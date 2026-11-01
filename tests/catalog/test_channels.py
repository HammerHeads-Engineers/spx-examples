import pytest
import yaml

from tools.model_catalog import ROOT, CatalogError, build_document
from tests.catalog.test_distribution import baseline, source


def test_stable_defers_ble_without_removing_community_examples():
    stable = build_document(ROOT, "test-stable", channel="stable")
    preview = build_document(ROOT, "test-preview", channel="preview")
    source_entries = yaml.safe_load(
        (ROOT / "library/catalog/models.yaml").read_text(encoding="utf-8")
    )["models"]
    deferred = {
        m["id"]
        for m in source_entries
        if "stable"
        not in m.get("distribution", {}).get("channels", ["preview", "stable"])
    }
    assert {"Embedded.HealthMonitor.BleGatt", "Embedded.TempSensor.BleGatt"} <= deferred
    assert {m["id"] for m in preview["models"]} - {
        m["id"] for m in stable["models"]
    } == deferred
    assert len(stable["models"]) == len(preview["models"]) - len(deferred)
    paths = {file["path"] for file in stable["files"]}
    assert not any(m["path"] in paths for m in preview["models"] if m["id"] in deferred)
    pack = next(p for p in stable["packs"] if p["id"] == "embedded_lab_pack")
    assert "ble" not in pack["default_protocols"]
    assert not any(i["model"] in deferred for i in pack["default_instances"])
    assert not {"spx_temp_sensor_ble", "spx_health_monitor_ble"} & set(
        pack["start_instances"]
    )
    assert all(
        (ROOT / m["path"]).is_file() for m in preview["models"] if m["id"] in deferred
    )


@pytest.mark.parametrize(
    "channels", [[], ["production"], ["stable", "stable"], "stable"]
)
def test_channel_policy_rejects_ambiguous_values(source, channels):
    path = source / "library/catalog/models.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["models"][0].setdefault("distribution", {})["channels"] = channels
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(CatalogError, match="distribution.channels"):
        build_document(source, "bad")
