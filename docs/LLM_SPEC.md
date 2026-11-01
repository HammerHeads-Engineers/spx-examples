# Model authoring rules for people and agents

This playbook owns public-library conventions: how to adapt a model, name its
state and integrate it into the catalog. The [model-language reference](MODEL_LANGUAGE.md)
owns syntax and runtime semantics. It is generated from `spx-docs`; propose new
constructs or semantic corrections upstream rather than editing that snapshot.

For a durable contribution follow [CONTRIBUTING.md](../CONTRIBUTING.md). For a
local live result follow [RUNTIME_WORKFLOW.md](RUNTIME_WORKFLOW.md). Agent mode
selection is defined once in [AGENTS.md](../AGENTS.md).

## Start from behavior, then adapt the interface

Choose the closest behavioral twin before creating a model. Preserve its physics,
actions, scenarios and public state unless the requested device needs a different
behavior. For a thermal controller, adapting a working controller's register map
is usually preferable to rebuilding its process dynamics.

For vendor/protocol models, cite first-party documentation and identify the
smallest useful point set: measured value, setpoint, output, mode/run state and
necessary status. Implement a full register map only when requested. Describe
any runtime-compatible bridge for command semantics and any unmodeled behavior.

Use the scaffold command in CONTRIBUTING to create a draft. A copied/generated
file still needs review of units, control semantics, bindings, endpoints and tests.
Do not change an unrelated model's behavior as part of a tooling/documentation task.

## Distinguish identifiers

| Identifier | Convention for new content | Example |
| --- | --- | --- |
| Catalog model ID | Stable discovery identity; retain existing dotted IDs | `Process.ThermalController.Modbus` |
| YAML file stem and `name` | Matching `lower_snake_case`, optional `__protocol` suffix | `thermal_controller__modbus` |
| New instance key | Descriptive ASCII `lower_snake_case`, unique on its server | `thermal_controller_demo` |
| Attribute | `lower_snake_case` with semantic prefix and unit when applicable | `k__target_temperature_c` |
| Supported binding/mapping name | Explicit, stable and unique in its container; prefer verb-led names | `publish_temperature`, `set_target`, `query_status` |

Existing public names, IDs and paths may follow legacy conventions. Preserve them
when compatibility is required. Deprecate with a replacement reference and retain
usable older releases instead of silently renaming a maintained interface.
Use 2-space YAML indentation, no tabs, and include `name`, `description` and
`attributes` in new/updated model definitions.

## State and units

| Attribute group | Meaning | Examples |
| --- | --- | --- |
| `k__*` | Persistent user/protocol control or simulation input | Setpoint, target, mode, enable flag |
| `cmd__*` | Action or trigger input | Start, stop, acknowledge, open/close request |
| Plain name | Telemetry, derived value, diagnostic or status readback | `temperature_c`, `power_kw`, `alarm_active` |
| Leading `_` | Internal helper state | `_elapsed_step_s` |

Use `k__` for a persistent target/mode that can be read back, and `cmd__` for an
action edge. Derived values, pure telemetry and helpers do not receive `k__`.
These prefixes express intent; they do not implement access control.

Prefer typed attributes with `type`, `default` and `unit` where applicable. Keep
the name suffix and explicit unit aligned: `temperature_c` / `degC`,
`pressure_mbar` / `mbar`, `energy_total_kwh` / `kWh`. Useful suffixes include
`_pct`, `_ms`, `_s`, `_hz`, `_khz`, `_v`, `_a`, `_ma`, `_w`, `_kw`, `_wh`, `_kwh`,
`_va`, `_kva`, `_var`, `_bar`, `_ppm`, `_nm`, `_nm_s` and `_sccm`.

## Communication parameters

`meta_parameters` belongs in ordinary device models whenever deployment values
vary across instances. Bind configurable transport fields with `$param(...)`.
Keep simulation tuning and ordinary control state in `attributes`.

| Interface | Typical deployment parameters |
| --- | --- |
| ASCII / SCPI | `ascii_port`; prefer default `0` for automatic assignment |
| Modbus | Host, `modbus_port`, `modbus_unit_id` when supported |
| MQTT | `mqtt_broker_host`, `mqtt_broker_port`, instance topic prefix |
| LwM2M | Endpoint ID, server host/ports and local endpoint/port |
| BLE | `ble_adapter_base_url`, `ble_device_name` |
| HTTP | Host and port |
| OCPP | Server host, port, path and charge-point identity |

The [canonical communication example](MODEL_LANGUAGE.md#communication) shows
parameterized MQTT and named bindings. Inspect the nearest actual protocol model
for its complete adapter fields. Do not hardcode instance-level endpoints or IDs.
If an entry spans several attributes, a stable protocol-point name such as
`modbus_hr_40001` is also appropriate. Use direction suffixes only to disambiguate.

Before finishing, audit every configurable communication block. When fixing a
shared family/protocol problem, check sibling models and make a consistent,
non-breaking cleanup where safe. Preserve legacy defaults/public names that
existing clients require.

## Actions, scenarios and time

Use the structures and expressions defined in the model reference: actions and
conditions as lists, scenarios as a mapping, and list-form communication for new
work. Use supported hooks/imports; do not infer language rules from a legacy file.
`meta_parameters` and `init_parameters` can belong to device models. System
containers such as instances, connections and snapshots belong to system config.

Regular demonstration scenarios are opt-in. Set `enabled: true` only when
automatic startup is an intentional model requirement. Give user-facing scenarios
a description/display name. Use their local timer for scenario-relative phases;
`__timer` is reserved instance elapsed time, not a scenario clock. Time-aware
actions need a model timer or an explicitly provided time source. Follow the
[scenario reference](MODEL_LANGUAGE.md#scenarios) for exact semantics.

## Repository integration

Put model YAML in `library/domains/<domain_group>/<device_class>/<vendor>/`.
The domain groups are `building`, `environment`, `industrial`, `energy`, `lab`;
device class and vendor are `lower_snake_case`, with `generic` where appropriate.

For a public contribution add/update its catalog entry, relevant pack membership,
documentation and meaningful tests. Update a profile when its runnable example
changes. Put required helpers/resources in the catalog's `distribution.resources`;
server compatibility, channels, licensing and deprecation also belong to catalog
metadata. See [the catalog contract](CATALOG_CONTRACT.md). Never place model YAML
under `library/industries/<pack>/` or hand-edit generated `MODELS.yaml` indexes.
Refresh derived files with `poetry run python -m tools.catalog refresh`.

## Reference models and starters

| Need | Inspect |
| --- | --- |
| Minimal control → telemetry | [Temperature starter](../templates/models/temperature_sensor.yaml) and [runnable tutorial](../examples/README.md) |
| Modbus control adaptation | [Thermal controller](../library/domains/industrial/controller/generic/thermal_controller__modbus.yaml) |
| Reusable physics/actions | [Advanced thermal controller](../library/domains/industrial/controller/generic/thermal_controller_advanced.yaml) |
| MQTT telemetry and discovery | [WAGO/Vaisala weather gateway](../library/domains/environment/gateway/wago_vaisala/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml) |
| BACnet controls and scenarios | [Flexit Nordic HVAC](../library/domains/building/controller/generic/hvac_flexit_nordic__bacnet.yaml) |
| Modbus metering | [iEM3000 meter](../library/domains/energy/meter/schneider/energy_meter_iem3000__modbus.yaml) |
| KNX multi-channel behavior | [ABB cover actuator](../library/domains/building/actuator/abb/abb_jra_s4_230_5_1__knx.yaml) |

These are starting points, not exceptions to current conventions. Validate the
adapted behavior and the claimed transport separately. The [behavior test template](../templates/tests/test_temperature_behavior.py.example)
demonstrates an isolated runtime assertion and cleanup. Use the installed
`spx-python` guide as described in [examples](../examples/README.md#sdk-and-mcp-reference).

## Operational flow for new-device-model generation automations

The automation-specific dedupe, branch, CI remediation and escalation procedure
is maintained in [AUTOMATION.md](AUTOMATION.md). It applies to model-generation
automations, not every repository or live-runtime task. Keep prompts focused on
the requested device, constraints and acceptance criteria; link shared rules.
