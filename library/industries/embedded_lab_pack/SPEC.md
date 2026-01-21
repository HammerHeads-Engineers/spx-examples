# Embedded & Lab Pack SPEC

Purpose: BLE/LwM2M/MQTT edge nodes and SCPI/Modbus instruments for CI pipelines and firmware validation labs.

## Scope
- Profiles: `profiles/embedded_lab_pack/mhealth_ci.yaml`, `profiles/embedded_lab_pack/scpi_lab.yaml`
- Tests: `tests/packs/embedded_lab_pack/integration`
- Catalog entry: `library/catalog/industries.yaml` (embedded_lab_pack)

## When adding or updating models in this pack
1. Add or update model YAML under `library/domains/...`.
2. Update `library/catalog/models.yaml` (include `packages: [embedded_lab_pack]` and any relevant `profiles`).
3. Update `library/catalog/industries.yaml` if default instances or services need changes.
4. Update `profiles/embedded_lab_pack/mhealth_ci.yaml` or `profiles/embedded_lab_pack/scpi_lab.yaml` if the quickstart should include the model.
5. Update `library/industries/embedded_lab_pack/README.md` if the pack scope or model list changes.
6. Add or update tests under `tests/packs/embedded_lab_pack/`.

## Validation
```bash
poetry run python tools/validate_models.py
poetry run pytest tests/packs/embedded_lab_pack
```
