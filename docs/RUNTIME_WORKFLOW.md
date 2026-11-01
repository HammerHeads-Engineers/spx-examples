# Work with a live SPX server

Use this route when the user wants a working local simulation, instance, scenario,
diagnostic result or connection. [AGENTS.md](../AGENTS.md) defines mode resolution.
A runtime task can happen in a full checkout; MCP availability alone does not
make every task a runtime task.

## Select the result and environment

Identify the user's intended server, existing model/instance and requested outcome.
Inspect the live state before changing it. Use the already configured host-managed
MCP tools and authorization. Product installation and client setup are covered by
the [product MCP guide](https://docs.simplephysx.com/llm-first-model-authoring/connect-llm-with-spx-mcp);
the [offline reference](MCP.md) describes tool inputs and outputs.

Runtime work is local to that server/workspace unless persistence was requested.
Do not automatically add public catalog entries, pack/profile updates, README
changes or pytest suites. A runtime-only adjustment to an existing instance can
usually be completed without editing model YAML.

## Use an existing model or instance

1. Inspect models/instances and exact attribute names using the available catalog
   and `server_list_instances`, `server_get_instance`, `server_get_attrs` tools.
2. Prefer MCP `server_*` lifecycle tools to register, ensure, recreate, reset or
   start the requested instance. Recreate only when the requested change needs it.
3. Confirm the instance reaches `RUNNING`. For diagnostics or control tasks,
   verify the specific observation/change requested by the user.
4. Report model ID, instance key, state and endpoint details needed to use it.

Stop at that result. Protocol read/write tests, longer diagnostics and public
library changes are additional work when requested or needed to diagnose a failure.
`RUNNING` proves startup; it does not establish vendor fidelity or wire compatibility.

## Create a local model from a manual

Read the [authoring rules](LLM_SPEC.md) and [language reference](MODEL_LANGUAGE.md)
before substantive YAML work. Use the closest behavioral twin and preserve its
physics/actions/scenarios while adapting metadata, units and protocol mapping.
For thermal controllers, begin with an existing controller rather than rebuilding
its behavior by default.

Extract the smallest useful point set from the first-party manual: measured value,
setpoint, output, mode/run-stop and essential status. Avoid a full register-map
implementation unless requested. If commands need a small runtime-compatible
bridge, document that choice in the model description.

Validate early through the host's model-validation tool. In a repository checkout,
`poetry run python tools/validate_models.py` is the structural fallback. Then
register the model, recreate/start its instance and confirm `RUNNING`. Update the
local catalog only if discovery requires it. Do not add pytest or pack integration
work to this fast path unless the user requests a durable contribution.

Prefer high-level MCP operations. If an optional helper prevents registration,
fall back promptly to the supported client/API path rather than investigating
unrelated helper internals. Inspect the actual instance document when tree layout
is unclear; do not keep trying guessed attribute paths.

## Diagnostics and scenarios

Use `server_get_*`, `server_set_*`, `server_ramp_attr` and runtime scenario tools
for the shortest proof of the requested behavior. Run scenarios and attribute
ramps on the chosen instance. Persist them to model YAML only when requested.
Protocol probes are opt-in or failure-driven; if performed, report the actual
endpoint, tested direction and observed result separately from lifecycle state.

## Connect existing instances

Requests such as "make X affect Y" or "feed this measurement into that model"
normally mean a runtime connection rather than a model rewrite.

1. Discover exact instance keys and attributes. Prefer telemetry/calculated outputs
   as the source and persistent `k__*` inputs as the target. Continuous propagation
   into `cmd__*` is appropriate only for an explicitly requested trigger behavior.
2. Inspect connections with `server_list_connections` / `server_get_connection`.
3. Use `server_upsert_connection` with structured endpoint arguments:

   ```text
   connection_name: weather_to_pv
   source_instance_key: <discovered weather instance>
   source_attr_path: brightness_lux
   target_instance_key: <discovered PV instance>
   target_attr_path: k__illuminance_lux
   replace: true
   start: true
   ```

   Source `from` reads `$out(source.attribute)`; target `to` writes
   `$in(target.attribute)`. Use handwritten expressions only for custom behavior.
4. Ensure the global connections container is running with
   `server_start_connections`. Use `server_start_connection` for an individual
   connection. Imported/restored objects can remain `INITIALIZED`; recheck both
   connection and container after restore before expecting propagation.
5. Change the source or call `server_run_connection`, then verify the target.

Success means the connection is `RUNNING`, `propagation_status` is `ACTIVE` when
available, and a source change/run actually updates the target. Use
`server_delete_connection` only when removing a connection is part of the task.

## Promote a live result into the shared library

When the user asks for persistence, follow [CONTRIBUTING.md](../CONTRIBUTING.md):
review public interfaces, parameterize deployment values, add catalog/resources
and meaningful tests, refresh generated files and run the shared checks. A live
experiment's successful startup alone is not release-grade qualification.
