# Industrial Pack (Industry 4.0) SPEC

Purpose: OPC UA/Modbus/MQTT/HTTP kit for line automation, process control, and factory monitoring.

## Scope
- Profiles: `profiles/industrial_iiot_pack/process_cell_quickstart.yaml`, `profiles/industrial_iiot_pack/iiot_monitoring.yaml`
- Tests: `tests/packs/industrial_iiot_pack/integration`
- Catalog entry: `library/catalog/industries.yaml` (industrial_iiot_pack)

## When adding or updating models in this pack
1. Add or update model YAML under `library/domains/...`.
2. Update `library/catalog/models.yaml` (include `packages: [industrial_iiot_pack]` and any relevant `profiles`).
3. Update `library/catalog/industries.yaml` if default instances or services need changes.
4. Update `profiles/industrial_iiot_pack/process_cell_quickstart.yaml` or `profiles/industrial_iiot_pack/iiot_monitoring.yaml` if the quickstart should include the model.
5. Update `library/industries/industrial_iiot_pack/README.md` if the pack scope or model list changes.
6. Add or update tests under `tests/packs/industrial_iiot_pack/`.

## Golden references
- `library/domains/industrial/controller/generic/thermal_controller_advanced.yaml`: control-loop patterns shared across packs.

## Validation
```bash
poetry run python tools/validate_models.py
poetry run pytest tests/packs/industrial_iiot_pack
```
