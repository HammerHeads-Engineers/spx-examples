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
- When writing tests that use the `spx_python` client, follow `SPX_PYTHON_LLM.md` (the single source of truth shipped with the spx-python package).
- Add scenario `description` or `display_name` for user-facing scenarios.
- If you use time-aware actions (`ramp`, `saw`, `interpolate`, `pid`), include `timer` config
  or confirm the stack provides a timer component.
- Keep YAML formatting consistent (2-space indentation, no tabs).
- Update pack README files when a pack changes.
- Use `meta_parameters` primarily for communication/protocol parameterization (e.g., addresses, ports, topics) to support multi-instance generation; avoid placing tuning knobs there unless they must be provisioned per instance or the client explicitly requests it.

## MAY
- Add helper tooling in `tools/` if it does not change runtime behavior.
- Add new packs or profiles with matching catalog updates.

## Operational flow for new-device-model generation automations
Use this flow only for automations whose primary objective is creating a new
device model YAML (plus required integration updates such as catalog/profile/tests).
Do not treat this as a mandatory flow for unrelated repository tasks.

1) Input contract
- Start from a clear objective and acceptance criteria.
- Confirm target domain/pack and protocol.
- For vendor/protocol-specific models, require first-party documentation links.

2) Implementation scope
- Add/update model YAML in `library/domains/...`.
- Keep naming rules (`lower_snake_case`, `name` aligned with file stem).
- Update catalogs/profiles/pack docs as required by AGENTS.md.
- Register the model in the target pack explicitly:
  - add `packages: [<target_pack>]` in `library/catalog/models.yaml`,
  - include the model in at least one target-pack profile in `profiles/<target_pack>/*.yaml`,
  - if one-click sample provisioning is expected for the pack, add `default_instances` (and `start_instances` when needed) in `library/catalog/industries.yaml`.
- Keep changes additive and backward-compatible.

3) Runtime smoke gate (required)
- Add a minimal integration smoke test for each new model.
- Smoke test must load/register the model via `spx_python`, create/reset/start an instance, and assert it reaches `running`.
- For protocol models, verify at least one protocol-level read/write probe on the exposed endpoint (for Modbus: resolve endpoint and read key registers).
- On failure, capture diagnostic context from instance state and CI logs.
- Place the smoke test under the target pack integration suite (`tests/packs/<target_pack>/integration/`).

4) Validation before push
- Run:
  - `poetry run python tools/validate_models.py`
  - `poetry run pytest`

5) CI remediation loop
- After push, monitor CI for the branch.
- If CI fails: fetch failing job logs, apply targeted fixes, commit, and push on the same branch.
- Retry CI remediation up to 3 consecutive attempts.

6) Process upgrade gate (required for new-model workflow)
- Keep or add a CI-visible guard that enforces: new model YAML changes must include runtime smoke coverage in the target pack integration tests.
- The guard may be implemented as a pytest check, validation script check, or equivalent repository-native CI check.
- If the guard fails, treat it as a blocker and fix it before opening/updating the PR.

7) Success path
- Open or update a PR with base branch `develop` only.
- Never target `main` from automation.
- Include source links, rationale, and test/validation evidence in the PR body.

8) Failure fallback (after 3 failed CI remediation attempts)
- Stop automated fix attempts.
- Open an issue in the repository summarizing:
  - branch and commit,
  - failing workflow/job URLs,
  - last observed error signature,
  - attempted fixes,
  - explicit blocker and next recommended manual action.
- Leave merge from `develop` to `main` to a human maintainer.

## Prompt minimization guidance
- Keep automation prompts short.
- Put stable process rules in this file and reference them from prompts.
- Prompt content should focus on task-specific objective, constraints, and deliverables.
- Avoid repeating generic flow, branch policy, and retry policy in every automation prompt.
- For new-device-model generation prompts, reference this section instead of duplicating it.

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

Command vs state naming (k__ vs cmd__):
```yaml
attributes:
  k__position_pct: 0.0      # key state: current position (readable in UI)
  k__target_pct: 50.0       # key state: desired position (telemetry/target)
  cmd__move_long: 2         # command input: 0=down, 1=up, 2=idle
  cmd__stop: 0              # command input: 1=stop
actions:
  - function: $in(cmd__move_long)
    name: apply_move
    call: (
          1 if $in(cmd__move_long) == 1
          else -1 if $in(cmd__move_long) == 0
          else 0
        )
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
- Attribute naming: stick to `lower_snake_case` (`a-z0-9_`, no spaces or special chars). Leading `_` marks helper/hidden attributes; use `k__` prefix (double underscore separator) to mark primary/simulation-critical attributes (UI may strip the prefix for display). For command/trigger inputs, prefer the `cmd__` prefix (e.g., `cmd__move_long`, `cmd__stop`); keep legacy `*_cmd` names only when required for backward compatibility or existing integrations.
- Use `$in`, `$out`, `$attr`, `$ext`, and `#attr(...)` consistently with existing models.
- Use `hooks`, `python_file`/`import`, and `if_chain` only as documented in `docs/MODEL_LANGUAGE.md`.
- Stick to communication protocol types listed in `docs/MODEL_LANGUAGE.md` unless the runtime adds new ones.
- Timer access: use the reserved private attribute `__timer` only for model-instance elapsed time
  (mirrors the model timer time in seconds). Do not define `__timer` yourself; it exists only on model instances.
  Writing to `__timer` sets timer time and stops the timer if running.
- Scenario timing: in scenario `conditions` and action expressions, use the scenario-local timer
  (`$attr(timer.time)` or `$(.timer.time)`), which starts at 0 on each scenario run.
  Do not use `__timer` for scenario-relative phases.

### `k__` attribute guidance
Use `k__` to mark the primary control inputs of a model:
- User-settable setpoints, targets, and modes (e.g., temperature setpoints, operating modes).
- Enable/disable flags or other switches that change system behavior.
- Attributes written via external protocols (e.g., BACnet `write`) that drive control logic.

Avoid `k__` for:
- Derived/calculated values (e.g., `active_*`, `*_demand`, `*_load_pct`).
- Pure telemetry outputs, diagnostics, or helper/internal attributes.

## Scenario timer guidance
- Use the scenario-local timer: `timer.time` is elapsed seconds since the scenario started.
- In conditions and call expressions, reference it as `$attr(timer.time)` or `$(.timer.time)` (explicit local scope).
- Do not use `__timer` for scenario-relative phases. `__timer` mirrors the instance timer and is unrelated to scenario start.
- To reference the parent/root timer from inside a scenario, use `$attr(..timer.time)` (parent) or `$attr(~.timer.time)` (root).
- The scenario timer resets and starts on each scenario `start()` and stops on `stop()`. Expect it to restart from 0 on every run.
- Do not set `enabled: true` in regular scenario definitions, because that auto-starts the scenario when the instance starts.
  Only set `enabled: true` when the model explicitly requires auto-start behavior.

Example:
```yaml
scenarios:
  thunderstorm:
    display_name: "Thunderstorm"
    duration: 40.0
    conditions:
      - if: $attr(timer.time) < 10.0
        actions:
          - function: $in(k__outdoor_temperature_c)
            params: {temp: 28.0}
            call: temp
      - if: ($attr(timer.time) >= 10.0) and ($attr(timer.time) < 25.0)
        actions:
          - function: $in(k__outdoor_temperature_c)
            params:
              temp_start: 28.0
              temp_end: 20.0
              ramp_start: 10.0
              ramp_duration: 15.0
            call: |
              (lambda t:
                temp_start + (temp_end - temp_start) * min(1.0, max(0.0, (t - ramp_start)) / ramp_duration)
              )($attr(timer.time))
      - if: $attr(timer.time) >= 25.0
        actions:
          - function: $in(k__outdoor_temperature_c)
            params: {temp: 21.0}
            call: temp
```

## Naming rules (SPX)
Always use consistent, deterministic names. No randomness.

1) Models / components
- Class/model identifiers: PascalCase, ASCII (e.g., `TemperatureSensor`, `HvacController`).
- Instance/component identifiers: snake_case, ASCII (e.g., `temperature_sensor`, `hvac_controller_1`).
- Avoid spaces, dots, and special characters; allow only `[a-z0-9_]`.
- Note: file names and YAML `name` fields remain `lower_snake_case` per the rules above.

2) Bindings
- Every binding must have an explicit `name` when the protocol supports it.
- `name` must be stable and unique within its `bindings` container.
- Prefer `name` equal to the attribute name (e.g., binding `temperature` for attribute `temperature`).
- If a binding covers multiple attributes or the protocol address is the primary identity,
  use a protocol-point name (e.g., `knx_ga_1_1_10`, `modbus_hr_40001`).
- Add direction suffix only when it helps disambiguate: `_in`, `_out`, `_rw` (e.g., `temperature_out`).

3) Mapping (legacy/conversion inputs)
- If mapping is a dict: key = attribute name and is the primary source for naming.
- When mapping entries support a `name` field, set it explicitly:
  `name` defaults to the mapping key (e.g., `attr_name`).
- If mapping is a list: always include `name` on every entry.
- Prefer attribute names over protocol patterns unless uniqueness requires otherwise.

## PR checklist
- [ ] `python tools/validate_models.py` passes
- [ ] `pytest` passes (or document why it was not run)
- [ ] Catalogs updated (`library/catalog/*.yaml`)
- [ ] Pack docs and profiles updated when applicable
- [ ] No breaking changes introduced
