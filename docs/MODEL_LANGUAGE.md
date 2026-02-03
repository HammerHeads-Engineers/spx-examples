# MODEL_LANGUAGE

This document defines the lightweight YAML modeling language used in this repo.
It is descriptive, not a strict schema; update it if new constructs are introduced.

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
- System components (advanced): `connections`, `modules`, `meta_parameters`, `init_parameters`,
  `instances`/`units`, `templates`/`models`, `snapshots`, `logs`.

System components are typically used in system-level configs; avoid them in per-model YAML
unless the model explicitly needs them.

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
- `$in(attr)` reads a value from the model state.
- `$out(attr)` writes a value to the model state.
- `$attr(path)` reads runtime metadata (e.g., `$attr(timer.time)`).
- `$ext(attr)` exposes raw values for protocol bindings.
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

If you introduce a new action type, document it here and add a usage example.

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
`communication` is a list of protocol blocks. Each block is a mapping keyed by the protocol name:
```yaml
communication:
  - mqtt:
      broker: mosquitto-server
      port: 1883
      bindings:
        - attribute: $ext(temperature_c)
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
- Prefer `name` equal to the attribute name (e.g., `temperature` for `$ext(temperature)`).
- If a binding spans multiple attributes or the protocol address is the primary identity,
  use a protocol-point name (e.g., `knx_ga_1_1_10`, `modbus_hr_40001`).
- Add direction suffix only when needed to disambiguate: `_in`, `_out`, `_rw`.

For mappings expressed as dicts:
- The mapping key is the primary name.
- If the entry supports a `name` field, set it explicitly (defaulting to the mapping key).

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
    enabled: true
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
