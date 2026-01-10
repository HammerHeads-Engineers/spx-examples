# Smart-Building Pack (BMS) SPEC

Purpose: multi-protocol BMS/BAS demo pack covering HVAC, lighting, safety, energy, and telemetry.

## Scope
- Profile: `profiles/smart_building_pack/bms_quickstart.yaml`
- Tests: `tests/packs/smart_building_pack/integration`
- Catalog entry: `library/catalog/industries.yaml` (smart_building_pack)

## When adding or updating models in this pack
1. Add or update model YAML under `library/domains/...`.
2. Update `library/catalog/models.yaml` (include `packages: [smart_building_pack]` and any relevant `profiles`).
3. Update `library/catalog/industries.yaml` if default instances or services need changes.
4. Update `profiles/smart_building_pack/bms_quickstart.yaml` if the quickstart should include the model.
5. Update `library/industries/smart_building_pack/README.md` if the pack scope or model list changes.
6. Add or update tests under `tests/packs/smart_building_pack/`.

## Golden references
- `library/domains/iot/generic/hvac_flexit_nordic__bacnet.yaml`: BACnet object map with derived HVAC dynamics.
- `library/domains/weather/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml`: MQTT telemetry plus Home Assistant discovery payloads.
- `library/domains/iot/generic/energy_meter_iem3000__modbus.yaml`: Modbus register mapping with derived power metrics.
- `library/domains/iot/abb/abb_jra_s4_230_5_1__knx.yaml`: multi-channel KNX bindings with mirrored state.
- `library/domains/thermal_controllers/generic/thermal_controller_advanced.yaml`: control-loop patterns shared across packs.

## Validation
```bash
poetry run python tools/validate_models.py
poetry run pytest tests/packs/smart_building_pack
```
