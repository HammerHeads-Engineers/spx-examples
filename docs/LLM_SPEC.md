# LLM_SPEC

Single source of truth for LLM and agent contributions.

## MUST
- Keep runtime behavior unchanged unless the change is required for tooling or validation.
- Place new models under `library/domains/<domain>/<vendor|generic>/`.
- Follow `docs/MODEL_LANGUAGE.md` for YAML structure and expressions; update it if you add new constructs.
- Update `library/catalog/models.yaml` for every new model.
- Update `library/catalog/domains.yaml` and `library/catalog/services.yaml` if you add new domains or protocols.
- Update `library/catalog/industries.yaml` and related `profiles/<pack>/*.yaml` when adding to packs.
- Add or update tests in `tests/` (pack tests in `tests/packs/<pack>/`).
- Run validation (`python tools/validate_models.py`) and tests before opening a PR.

## SHOULD
- Start from the closest existing model and keep structure consistent.
- Keep file names `lower_snake_case`; for new or updated models, align `name` with the file stem.
- For new or updated models, include `name`, `description`, and `attributes` when feasible (legacy models may omit `name` or `description`).
- Consult `library/industries/<pack>/SPEC.md` when changing a specific pack.
- Add scenario `description` or `display_name` for user-facing scenarios.
- If you use time-aware actions (`ramp`, `saw`, `interpolate`, `pid`), include `timer` config
  or confirm the stack provides a timer component.
- Keep YAML formatting consistent (2-space indentation, no tabs).
- Update pack README files when a pack changes.

## MAY
- Add helper tooling in `tools/` if it does not change runtime behavior.
- Add new packs or profiles with matching catalog updates.

## Golden examples

Minimal model YAML:
```yaml
name: demo_sensor__mqtt
description: |
  Demo sensor for smoke tests.
attributes:
  temperature_c: 20.0
communication:
  - mqtt:
      broker: "host.docker.internal"
      port: 1883
      bindings:
        - attribute: $attr(temperature_c)
          topic: telemetry/temperature_c
          direction: publish
scenarios:
  warmup:
    enabled: true
    description: "Ramp temperature upward for demos."
    duration: 10.0
    overrides:
      $in(temperature_c): 30.0
```

Catalog entry:
```yaml
  - id: Demo.Sensor.Mqtt
    name: Demo Sensor (MQTT)
    path: library/domains/iot/generic/demo_sensor__mqtt.yaml
    domain: iot
    protocols: [mqtt]
    services:
      - id: mqtt_broker
    packages: [embedded_lab_pack]
    profiles: [mhealth_ci]
```

Profile:
```yaml
name: demo_profile
description: |
  Minimal demo of a single MQTT model.
models:
  - library/domains/iot/generic/demo_sensor__mqtt.yaml
services:
  - mqtt_broker
```

## Golden standards (reference models)
- `library/domains/iot/generic/hvac_flexit_nordic__bacnet.yaml`: rich attributes, multi-step actions, BACnet object map with states/units, scenario actions.
- `library/domains/weather/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml`: dual MQTT connections, availability, Home Assistant discovery payloads, condition-driven scenarios.
- `library/domains/thermal_controllers/generic/thermal_controller_advanced.yaml`: reusable action params/imports, conditions, and time-step aware control logic.
- `library/domains/iot/generic/energy_meter_iem3000__modbus.yaml`: clear Modbus input/holding register mapping with derived measurements.
- `library/domains/iot/abb/abb_jra_s4_230_5_1__knx.yaml`: consistent multi-channel state/action patterns with KNX bindings.

## Modeling language (short rules)
- Use top-level keys from `docs/MODEL_LANGUAGE.md` (`attributes`, `actions`, `conditions`, `communication`,
  `scenarios`, `hooks`, `python_file`/`import`, `timer`, `polling`). Advanced system sections
  (`connections`, `modules`, `meta_parameters`, `init_parameters`, `instances`/`units`,
  `templates`/`models`, `snapshots`, `logs`) belong in system-level configs.
- Keep `actions` and `conditions` as lists when present. Prefer list-form `communication` (legacy models may use a mapping).
- Keep `scenarios` as a mapping; use `overrides` for simple value swaps and `actions`/`conditions` for time-based logic.
- Prefer explicit units in attribute names (e.g., `_c`, `_pct`, `_ms`, `_kw`, `_kwh`).
- Use `$in`, `$out`, `$attr`, `$ext`, and `#attr(...)` consistently with existing models.
- Use `hooks`, `python_file`/`import`, and `if_chain` only as documented in `docs/MODEL_LANGUAGE.md`.
- Stick to communication protocol types listed in `docs/MODEL_LANGUAGE.md` unless the runtime adds new ones.

## PR checklist
- [ ] `python tools/validate_models.py` passes
- [ ] `pytest` passes (or document why it was not run)
- [ ] Catalogs updated (`library/catalog/*.yaml`)
- [ ] Pack docs and profiles updated when applicable
- [ ] No breaking changes introduced
