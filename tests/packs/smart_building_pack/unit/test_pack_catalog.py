# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root
from tests.shared.pack_catalog import (
    find_industry,
    load_catalog_services,
    load_yaml,
    model_index_by_id,
    model_index_by_path,
    models_for_pack,
)


PACK_ID = "smart_building_pack"
REQUIRED_SMOKE_TESTS = {
    "Energy.EnergyMeterEatonPxm2000.Modbus": (
        "tests/packs/smart_building_pack/integration/test_modbus_pxm2000_smoke.py"
    ),
}


def test_pack_catalog_models_exist_and_load() -> None:
    root = repo_root()
    models = models_for_pack(PACK_ID, root=root)
    assert models, f"No catalog models found for pack {PACK_ID!r}"

    for entry in models:
        path_str = entry.get("path")
        assert isinstance(path_str, str) and path_str, f"Invalid model path entry: {entry!r}"
        path = root / path_str
        assert path.exists(), f"Catalog model path does not exist: {path_str}"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict), f"Model YAML must be a mapping: {path_str}"


def test_pack_services_declared_in_catalog() -> None:
    services = {svc.get("id") for svc in load_catalog_services() if isinstance(svc.get("id"), str)}
    industry = find_industry(PACK_ID)
    for service_id in industry.get("services", []) or []:
        assert service_id in services, f"Unknown service id '{service_id}' in pack '{PACK_ID}'"


def test_pack_default_instances_reference_known_models() -> None:
    models_by_id = model_index_by_id()
    industry = find_industry(PACK_ID)
    for inst in industry.get("default_instances", []) or []:
        if not isinstance(inst, dict):
            continue
        model_id = inst.get("model")
        if model_id:
            assert model_id in models_by_id, f"Default instance references unknown model id '{model_id}'"


def test_pack_start_instances_fit_community_license_limit() -> None:
    industry = find_industry(PACK_ID)
    start_instances = industry.get("start_instances", []) or []
    assert len(start_instances) <= 5, "Smart Building Pack starter must fit the Community license limit."
    assert start_instances == [
        "HVAC_Flexit_Nordic_BACnet",
        "Energy_Meter_iEM3000_Modbus",
        "Victron_Cerbo_GX_ESS_Modbus",
        "Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT",
        "Building_Physics",
    ]


def test_pack_profiles_reference_catalog_models() -> None:
    root = repo_root()
    models_by_path = model_index_by_path()
    industry = find_industry(PACK_ID)
    for profile_rel in industry.get("profiles", []) or []:
        if not profile_rel:
            continue
        profile_path = root / str(profile_rel)
        assert profile_path.exists(), f"Profile path does not exist: {profile_rel}"
        profile_doc = load_yaml(profile_path) or {}
        assert isinstance(profile_doc, dict), f"Profile YAML must be a mapping: {profile_rel}"
        for model_path in profile_doc.get("models", []) or []:
            assert model_path in models_by_path, (
                f"Profile '{profile_rel}' references model missing from catalog: {model_path}"
            )
            model_entry = models_by_path[model_path]
            packages = model_entry.get("packages", []) or []
            assert PACK_ID in packages, f"Catalog model {model_entry.get('id')} is missing '{PACK_ID}' in packages"


def test_required_pack_smoke_tests_are_present() -> None:
    root = repo_root()
    models_by_id = model_index_by_id()
    for model_id, smoke_rel in REQUIRED_SMOKE_TESTS.items():
        assert model_id in models_by_id, f"Required smoke-test model id is missing: {model_id}"
        smoke_path = root / smoke_rel
        assert smoke_path.exists(), f"Required smoke test is missing: {smoke_rel}"
