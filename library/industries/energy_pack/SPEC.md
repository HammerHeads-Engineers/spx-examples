# Energy Pack (e-Mobility & DER) SPEC

Purpose: energy-native DER / e-mobility demo pack with OCPP charge point + CSMS handshake, Modbus EVSEs, and power-meter telemetry.

## Scope
- Profiles: `profiles/energy_pack/ev_csms_demo.yaml`
- Tests: `tests/packs/energy_pack/integration`
- Catalog entry: `library/catalog/industries.yaml` (energy_pack)

## When adding or updating models in this pack
1. Add or update model YAML under `library/domains/...`.
2. Update `library/catalog/models.yaml` (include `packages: [energy_pack]` and any relevant `profiles`).
3. Update `library/catalog/industries.yaml` if default instances or services need changes.
4. Update `profiles/energy_pack/ev_csms_demo.yaml` if the quickstart should include the model.
5. Update `library/industries/energy_pack/README.md` if the pack scope or model list changes.
6. Add or update tests under `tests/packs/energy_pack/`.

## Golden references
- `library/domains/industrial/controller/generic/thermal_controller_advanced.yaml`: control-loop patterns shared across packs.

## Validation
```bash
poetry run python tools/validate_models.py
poetry run pytest tests/packs/energy_pack
```
