<!-- Generated from HammerHeads-Engineers/spx-docs@6ec09e4cad0b6cd958865bbd79b1b1b2833aa01c:simulation-and-modeling/model-definition-reference.md; do not edit. -->

> Canonical reference: [https://docs.simplephysx.com/reference/model-definition-reference](https://docs.simplephysx.com/reference/model-definition-reference)
> Source commit: `6ec09e4cad0b6cd958865bbd79b1b1b2833aa01c`. This complete offline snapshot follows the release baseline in spx-docs/sources.json.

# Model definition reference (YAML and JSON)

This is the canonical SPX model-definition reference. It describes the released
server RC76 / SDK RC21 baseline recorded in `sources.json`. Public examples and
repository conventions live in [spx-examples](https://github.com/HammerHeads-Engineers/spx-examples).
Its `docs/MODEL_LANGUAGE.md` is a generated offline copy of this page.

YAML and JSON express the same model mapping when passed through the API/import
path. JSON requires quoted keys and strings and has no YAML comments, anchors or
aliases. The public model library and catalogs use YAML; JSON support at the API
boundary does not change that repository convention.

## Minimal PT100-style model

YAML:

```yaml
name: pt100_demo
description: Minimal deterministic temperature sensor
attributes:
  k__temperature_c:
    type: float
    default: 20.0
    unit: degC
  temperature_c:
    type: float
    default: 20.0
    unit: degC
actions:
  - function: $in(temperature_c)
    name: update_temperature
    call: $in(k__temperature_c)
```

Equivalent JSON (API/import):

```json
{
  "name": "pt100_demo",
  "description": "Minimal deterministic temperature sensor",
  "attributes": {
    "k__temperature_c": {"type": "float", "default": 20.0, "unit": "degC"},
    "temperature_c": {"type": "float", "default": 20.0, "unit": "degC"}
  },
  "actions": [{"function": "$in(temperature_c)", "name": "update_temperature", "call": "$in(k__temperature_c)"}]
}
```

This models temperature telemetry, not the electrical resistance curve of a
physical PT100. Both serializations must parse to identical mappings. Catalog
validation is structural; registration and a running instance additionally test
runtime semantics. Protocol interoperability needs a separate explicit test.

## State naming

Use `lower_snake_case`. Use `k__*` for persistent control inputs and targets,
`cmd__*` for command/trigger inputs, plain names for telemetry and diagnostics,
and leading `_` for internal helpers. Prefixes express intent; they do not
implement access control. Keep dimensional suffixes and `unit` aligned, for
example `temperature_c` with `degC` or `energy_total_kwh` with `kWh`.


## Top-level structure
- `name`: optional string identifier (recommended for new/updated models).
- `description`: optional string describing the model.
- `attributes`: required mapping of model state.
- `actions`: optional list of action definitions applied every cycle.
- `conditions`: optional list of conditional rules.
- `communication`: optional list of protocol blocks.
- `scenarios`: optional mapping of scenario definitions.
- `hooks`: optional mapping of lifecycle/attribute hooks.
- `python_file` / `import`: optional Python class bindings.
- `timer`: optional time base for time-aware actions.
- `polling`: optional background runner for parent components.
- `meta_parameters`: per-instance/deployment inputs, including communication host, port and IDs.
- `init_parameters`: parameters consumed when constructing the model.
- System configuration (advanced): `connections`, `modules`, `instances`/`units`,
  `templates`/`models`, `snapshots`, `logs`.

### Deployment and communication parameters

`meta_parameters` belongs in an ordinary device model when its deployment values
vary between instances. Bind configurable adapter fields through `$param(...)`.
For example, this is a model fragment, not a complete definition:

```yaml
meta_parameters:
  modbus_port:
    type: int
    default: 502
communication:
  - modbus_slave:
      port: $param(modbus_port)
```

Provide the complete adapter host/unit/bindings from the chosen protocol reference.
Use attributes for simulation controls and telemetry, meta parameters for wiring.
System-only containers usually belong in system configuration rather than every
device definition. See the full Communication section for a complete example.

## Attributes
`attributes` is a mapping from attribute name to either:
- a scalar value (int/float/string/bool), or
- a typed mapping with `type` and `default`.

Example typed attribute:
```yaml
attributes:
  wind_direction_deg:
    type: int
    default: 180
```

Conventions:
- Use suffixes for units: `_c`, `_pct`, `_ms`, `_s`, `_kw`, `_kwh`, `_h`.
- Use `_cycle_time_s` when the model integrates over time; expose `cycle_time_s` only when the integration step must be user-visible.
- Internal helpers can be prefixed with `_`.
- Hidden helper attributes (prefixed with `_`) should generally be placed at the end of the `attributes` list.
- Use `k__` prefix for primary control inputs: setpoints, modes, enable/disable flags,
  or attributes that are written from external protocols and drive behavior.
  Avoid `k__` on derived or telemetry-only attributes.

## Expressions
- `$in(attr)` / `$internal(attr)` select the internal value wrapper for reads or writes.
- `$out(attr)` / `$ext(attr)` select the external value wrapper for reads or writes.
- `$attr(path)` reads runtime metadata (e.g., `$attr(timer.time)`).
- The action target or connection endpoint determines whether a wrapper is read or written; `in`/`out` alone are not read/write commands.
- `#attr(name)` references an attribute in protocol mappings.
- `$(...)` can reference runtime config values (commonly used in `params`), e.g. `$(~.timer.default_step)`.

## Actions
`actions` is a list. Each entry is a mapping with one action definition.
Common action shapes:
- `function`: compute and store a value.
- `noise`: inject noise into an output.
- `set`: set a value directly.
- `call`: invoke a component method on prepare/stop.
- `suspend`: temporarily disable components.
- `overrides`: temporarily override component/attribute values.
- `ramp` / `saw` / `interpolate` / `pid`: time-aware generators (require `timer`).

## Built-in actions (spx-core)
These action types are provided by spx-server/spx-core and used across the models in this repo:
- `function`: evaluates `call` (expression or block) and writes the result to the target.
- `set`: writes a literal value to the target (commonly used in `conditions`).
- `noise`: injects noise into the target; common fields include `type`, `std`, `mode`, plus optional `name`/`description`.
- `call`: invokes a method on a component during prepare/stop.
- `suspend`: disables target components during prepare; restores on stop.
- `override` / `overrides`: temporarily set component/attribute values; restores on stop.
- `ramp`: time-based ramp generator (linear or spline).
- `saw`: time-based sawtooth generator (regular or reverse).
- `interpolate`: interpolate a series of (time, value) points.
- `pid`: PID controller output based on `input` and `setpoint`.

New action types require runtime implementation and tests before they are documented as supported.

Common action fields (optional unless noted):
- Action key (e.g., `function`, `noise`, `call`, `ramp`): identifies the action type and target (required).
- `name`, `description`: human-friendly labels.
- `params`: reusable parameters for the action.
- `imports`: module imports for complex calculations (see below).
- `call`: expression or multi-line block used by `function`.
- `alpha`, `period`, `accel`, `decel`: model-specific tuning knobs.

Action details (spx-core):
- `call`: mapping with `path` (required), `args`, `kwargs`, and optional `stop_path`,
  `stop_args`, `stop_kwargs`. `path` is a dotted component path ending with a method name.
- `suspend`: mapping with `paths`/`targets`/`nodes` (string or list of strings),
  `fail_on_missing` (bool). Paths may use `.` or `/` separators; leading `/` targets root.
- `override` / `overrides`: mapping of path -> value, with optional `fail_on_missing`.
  Paths may be component paths or attribute references (`#`, `$`, `@`).
- `noise`: `type` ("white", "pink", "brownian"), `mean`, `std`, `size`,
  `output_type` ("float" or "int"), `mode` ("additive" or "proportional").
- `ramp`: `start_value`, `stop_value`, `duration`, `type` ("linear" or "spline"),
  `overshoot`, `stabilization_time`, `output_type`.
- `saw`: `start_value`, `stop_value`, `period`, `type` ("regular" or "reverse"),
  `output_type`.
- `interpolate`: `points` (list of `[time, value]`), `method` ("linear", "spline", etc),
  `fill_value` ("extrapolate" or literal), `output_type` ("float" or "int").
- `pid`: `setpoint`, `input`, `kp`, `ki`, `kd`.

Example (call action):
```yaml
actions:
  - call:
      path: "communication.modbus_tcp.detach"
      args: []
      kwargs: {}
      stop_path: "communication.modbus_tcp.attach"
```

Example (overrides action):
```yaml
actions:
  - overrides:
      actions.ramp.enabled: false
      /communication/mqtt/publish_interval: 0.5
      fail_on_missing: false
```

## Imports and extensions
Actions can import external modules or local helper functions via `imports`.
- External modules: `imports: {np: numpy}`.
- Local helpers: `imports: {thermal_step: "extensions.thermal_model.thermal_step"}`.
The `extensions/` package holds small, deterministic helper functions shared across models.
If you add a new helper or third-party dependency, keep it focused and update tooling/docs as needed.

Example:
```yaml
actions:
  - function: $in(temperature_c)
    name: update_temperature
    params:
      gain: 0.2
    call: $in(temperature_c) + gain * ($in(setpoint_c) - $in(temperature_c))
```

Example with local helper import:
```yaml
  - function: $in(temperature)
    imports: {thermal_step: "extensions.thermal_model.thermal_step"}
    params:
      dt: "$(~.timer.default_step) or $(~.polling.interval) or 0.25"
    call: |
      thermal_step(
        $in(temperature),
        $in(ambient),
        $in(heating_power),
        $in(heat_coeff),
        $in(cool_coeff),
        dt,
        mass=$in(thermal_mass),
      )
```

## Conditions
`conditions` is a list of conditional rules:
```yaml
conditions:
  - if: $in(temperature_c) >= $in(overload_threshold_c)
    actions:
      - set: $in(overload)
        value: 1
```

`if_chain` runs the first matching branch and supports `else`:
```yaml
if_chain:
  - if: $in(mode) == "auto"
    actions:
      - set: $in(target_speed)
        value: 3.0
  - else:
    actions:
      - set: $in(target_speed)
        value: 1.0
```

## Hooks
`hooks` registers hook components to run on lifecycle or attribute events.
Common events: `on_prepare`, `on_run`, `on_start`, `on_destroy`, `on_enable`, `on_disable`,
`on_event`, `on_set`, `on_internal_set`, `on_external_set`.
Common hook components: `refresh_model` (spx-sdk), `set_attr` (spx-core).

Example:
```yaml
hooks:
  on_set:
    - refresh_model
```

Example (attribute-level hooks, as used in spx-python tests):
```yaml
attributes:
  heating_power:
    default: 0.0
    hooks:
      on_set:
        - refresh_model
```

Example (set_attr hook):
```yaml
hooks:
  on_run:
    - set_attr:
        attribute: $in(overload)
        value: 1
```

## Python file imports
`python_file` (alias `import`) loads Python classes from local `.py` files and binds
attributes and lifecycle methods.
Paths should be workspace-relative (checked into the repo) and not absolute.

Example:
```yaml
python_file:
  path/to/mod1.py:
    class: FakeItemClass
    attributes:
      status:
        property: status
      int_value:
        property: int_value
      float_list:
        getter: float_list
        setter: float_list
    methods:
      start: start
      run:
        method: tick
        args: [3]
      pause: pause
      stop: stop
  path/to/mod2.py:
    class: InheritedItem
    attributes:
      count:
        property: count
      ids:
        getter: ids
        setter: ids
```

Example (argument binding from attributes, based on spx-sdk tests):
```yaml
python_file:
  path/to/mod1.py:
    class: FakeItemClass
    methods:
      run:
        method: tick
        args: ["$attr(value)"]
```

Example (init args/kwargs, based on spx-sdk tests):
```yaml
python_file:
  path/to/temp_param.py:
    class: ParamClass
    init:
      args: [5, 10]
      kwargs:
        scale: 2
```

## Communication

Deployment values belong in `meta_parameters`, bound with `$param(...)`, rather
than hardcoded endpoints. Keep simulation tuning in attributes. For the MQTT
fragment below, declare:

```yaml
meta_parameters:
  mqtt_broker_host: {type: str, default: localhost}
  mqtt_broker_port: {type: int, default: 1883}
```

`communication` is a list of protocol blocks. Each block is a mapping keyed by the protocol name:
```yaml
communication:
  - mqtt:
      broker: $param(mqtt_broker_host)
      port: $param(mqtt_broker_port)
      bindings:
        - name: publish_temperature
          attribute: $ext(temperature_c)
          topic: telemetry/temperature_c
          direction: publish
```

Bindings typically use `read_attribute` / `write_attribute` or `attribute` fields depending on protocol.
Legacy models may use a single mapping instead of a list; new or updated models should use the list form.
Known protocol types in spx-core include:
- `ascii`, `bacnet`, `ble`, `coap_server`, `dali`, `http_endpoint`, `knx_ip`,
  `knx_ip_simulator`, `lwm2m`, `matter`, `mbus`, `mbus_server`, `modbus_master`,
  `modbus_slave`, `modbus_tcp`, `mqtt`, `mqtt-ha`, `ocpp`, `opcua_server`,
  `profinet_server`, `profinet_snap7_adapter`, `redfish`, `redfish_server`,
  `snmp`, `snmp_server`.

### Binding naming conventions
When a protocol uses `bindings` (or another list of mapping entries that supports a `name` field):
- Include an explicit `name` on every binding entry.
- Keep `name` stable and unique within the container.
- Prefer stable verb-led names such as `publish_temperature`, `set_target` or `query_status`.
- If a binding spans multiple attributes or the protocol address is the primary identity,
  use a protocol-point name (e.g., `knx_ga_1_1_10`, `modbus_hr_40001`).
- Add direction suffix only when needed to disambiguate: `_in`, `_out`, `_rw`.

For mappings expressed as dicts:
- The mapping key is the primary name.
- If the entry supports a `name` field, set it explicitly (defaulting to the mapping key).

### OCPP response fields

OCPP payload field names may use a dotted path, for example
`idTagInfo.status: "#attr(k__authorization_status)"`, to populate a nested
response object. Generated response fields require SPX Server `v1.0.0-rc.73` or later:

```yaml
currentTime:
  attribute: "#attr(csms_current_time)"
  metadata: {generator: utc_now}
transactionId:
  attribute: "#attr(last_transaction_id)"
  metadata: {generator: transaction_id}
```

`utc_now` generates UTC at response construction. `transaction_id` allocates
a distinct positive integer for each response, scoped to one protocol instance.
The counter survives transport stop/start and restarts on instance recreation.
Generated values are also written to the mapped attributes for diagnostics.
Use generators only on the intended outbound response fields.

## Scenarios
`scenarios` is a mapping from scenario name to configuration.
Common fields:
- `enabled`: bool
- `duration`: number (seconds)
- `period`: number (seconds)
- `description` / `display_name`: strings
- `overrides`: mapping of `$in(...)` or dot-paths (e.g., `communication.mqtt.publish_interval`)
- `actions`: list of action definitions
- `conditions`: list of conditional rules

Guidance:
- Avoid `enabled: true` in standard scenario definitions because it auto-starts the scenario with instance start.
  Use `enabled: true` only when auto-start is explicitly required by the model specification.

Example:
```yaml
scenarios:
  warmup:
    enabled: false
    duration: 10.0
    overrides:
      $in(setpoint_c): 30.0
```

## Timer
`timer` configures the time base used by time-aware actions (`ramp`, `saw`, `interpolate`, `pid`).
Configuration keys:
- `initial_time`: starting elapsed time in seconds (default 0).
- `max_duration`: cap for elapsed time (default infinite).
- `resolution`: rounding step for the `time` property.
- `decimal_places`: rounding precision for `resolution`.
- `auto_reset`: if true, wraps on max_duration.
- `time_step` / `step`: default step increment for each run.

Example:
```yaml
timer:
  initial_time: 0.0
  max_duration: 3600
  resolution: 0.1
  decimal_places: 3
  auto_reset: false
  time_step: 0.25
```

### Private timer attribute (__timer)
Models that need elapsed time may use the reserved private attribute `__timer`:
- `__timer` mirrors the model's Timer component `time` value (elapsed seconds, monotonic).
- `__timer` exists only on model instances (not on the System root).
- Do not define your own attribute named `__timer` (reserved).
- Writing to `__timer` sets the timer time and stops it if running.

Reference it as `#attr(__timer)` / `$out(__timer)` in bindings or actions.

When to prefer `__timer` vs `$attr(timer.time)`:
- Use `__timer` for model-local elapsed time (instance uptime), especially in bindings or simple expressions where a single attribute reference is clearer.
- Use `$attr(timer.time)` (or `$(.timer.time)`) inside scenarios; it is the scenario-local timer that resets on each `start()`.
- Use `$attr(..timer.time)` (parent) or `$attr(~.timer.time)` (root) when you explicitly need non-scenario timers.

## Polling
`polling` runs the parent component's `run()` loop on a background thread.
Configuration keys:
- `interval`: base sleep interval in seconds (default 0.1).
- `jitter`: max random jitter added/subtracted from interval.
- `max_iterations`: max loop count before stopping (default infinite).

Example:
```yaml
polling:
  interval: 0.1
  jitter: 0.0
  max_iterations: 1000
```

## System components (advanced)
These appear in system-level configs more often than per-model YAML.
- `connections`: mapping of connection name -> `{from, to}` attribute references.
- `modules`: list of `{name: ModelClassName, ...}` for embedded model instances.
- `meta_parameters`: mapping of parameter name -> spec dict (type/required/default).
- `init_parameters`: mapping of attribute -> value to set at init time.
- `instances` / `units`: list or mapping of instances with `type` and optional `init_parameters`,
  plus nested `instances`.
- `templates` / `models`: mapping of template name -> model definition (registers a class).
- `snapshots`: snapshot config (`base_dir`, `persist_memory_to_disk`, `memory_subdir`).
- `logs`: log buffer config (`max_entries`, `level`, `format`, `datefmt`).

### System connections
Connections propagate values between attributes on live system components.

Use `from` for the source read endpoint and `to` for the target write endpoint:

```yaml
connections:
  Weather_Brightness_to_PV_Physics_Illuminance:
    from: $out(Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT.k__brightness_lux)
    to: $in(PV_Physics_Lux.k__illuminance_lux)
```

The source endpoint should normally be telemetry or a calculated output. The
target endpoint should normally be a persistent input, commonly a `k__*`
attribute. Use `cmd__*` targets only for explicit command or trigger behavior.

## Agent source order and runtime semantics

Read [Agent Start Here](https://docs.simplephysx.com/llm-first-model-authoring/agent-start-here)
and workspace AGENTS.md before authoring. Contribution naming rules live in the
public Examples modeling playbook; this canonical reference defines model syntax.
Examples are illustrative and do not override the specification or the documented
release baseline. There is no complete JSON Schema for arbitrary adapter/extension
fields: parsing and catalog validation are not proof of runtime or protocol success.

`$in`/`$ext` choose internal/external wrappers, not read/write permission. An
internal write clears an external override; persistent faults must be reapplied
at the intended point in execution. Snapshots restore structure/defaults, not
live readings or elapsed time. Manual clock control does not seed randomness.
For identifiers see the [glossary](https://docs.simplephysx.com/reference/glossary-of-terms#model-identifiers);
for verified stepping use the [client tutorial](https://docs.simplephysx.com/readme/using-spx-python).
