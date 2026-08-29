# Local MCP Tool

`spx-examples` includes a local MCP tool intended for code-oriented LLM workflows.
It is a repo tool, not an example project: the MCP server understands the local
catalog, profiles, packs, model validation rules, and a running SPX server.

## Scope

The current MCP server is designed for local `stdio` workflows:

- inspect repository packs, profiles, and models
- validate catalog models with the repository validator
- inspect models and instances on a running SPX server
- inspect runtime logs, communication trees, and protocol bindings
- optionally perform write operations such as model registration, instance lifecycle
  control, and attribute writes

## Work modes

The repository distinguishes two semantic work modes for MCP-capable LLM
agents:

- `runtime_mcp`: shortest reliable path to a live result on a local
  `spx-server`. Prefer MCP-first flows, avoid repo-wide hardening by default,
  and treat runtime changes as local unless the user explicitly asks to persist
  them.
- `repo_dev`: full repository development. Update models, tests, catalogs,
  docs, packs, and installer code as needed for durable repo changes.

These work modes are separate from the technical workspace shape:

- installer-managed MCP workspaces are bootstrapped as `runtime_mcp`
- full git checkouts are bootstrapped as `repo_dev`
- a manual repo checkout still defaults to `repo_dev`, even if MCP is available

Agents should resolve work mode in this order:

1. explicit user intent
2. `.spx/workspace_mode.toml`
3. legacy `.codex/workspace_mode.toml`
4. `.spx-mcp-workspace.json`
5. `repo_dev`

## Runtime requirements

- Python 3.10+ for the official `mcp` SDK
- project dependencies installed with dev extras
- `SPX_PRODUCT_KEY` for live server access
- `SPX_BASE_URL` if the server is not running at `http://localhost:8000`

The native Windows `.exe` and macOS `.pkg` installers select their bundled
Python 3.12 runtime when creating the MCP workspace. The MCP client then
launches the workspace `.venv` directly. Portable Linux `.run`/`.tgz` flows use
the host Python and require Python 3.10 or newer for MCP.

Example setup on Windows:

```powershell
poetry env use C:\Python314\python.exe
poetry install --with dev
```

## Bootstrap MCP client configs

To generate a local Codex MCP config for this repository without committing
machine-specific paths, use one of the bootstrap scripts below. They create
`<repo>/.codex/config.toml` and add local client config files to the worktree's
git exclude file.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_codex_mcp.ps1
```

Linux or macOS:

```bash
sh tools/setup_codex_mcp.sh
```

If you installed the macOS `.pkg`, you can also launch `SPX MCP Setup.app` from
`/Applications/SPX Tools/`. That companion app creates a workspace at
`~/Documents/SPX MCP Workspace`, prepares a local `.venv`, writes
`.codex/config.toml` for Codex, writes project-local `.mcp.json` for Claude
Code, and copies `CLAUDE.md` so Claude Code can follow `@AGENTS.md`. Both MCP
client configs point at the same local `spx-mcp` stdio server. They use
read/write mode by default. During setup you choose the work mode first:

- `runtime_mcp`: installer-managed MCP workspace copy
- `repo_dev`: full Git clone of `spx-examples` on `develop`

The setup flow also writes `.spx/workspace_mode.toml` so the workspace keeps a
local record of the intended mode. Existing `.codex/workspace_mode.toml` files
are still read as a legacy fallback. In git-backed workspaces, the setup updates
the local git exclude file so `.codex/config.toml`, `.mcp.json`, and
workspace-mode files do not show up in normal commits. Open the generated
workspace in Codex, Claude Code, or another MCP-capable client and start a fresh
session to pick up the local config.

## Runtime-first MCP workflow

Use this flow when the active work mode is `runtime_mcp`:

1. validate the touched model or payload with the smallest relevant repo check
2. register the model on the local SPX server early
3. create or recreate the runtime instance
4. start the instance and stop once it is `RUNNING`
5. report the minimal runtime result: model id, instance key, state, and any
   endpoint details relevant to the task
6. only then decide whether deeper protocol verification is needed

Do not spend time on broad repo cleanup, catalog work, pack integration, or
pytest coverage by default in `runtime_mcp`. Move to `repo_dev` only when the
user asks for a durable repository change.

For live runtime work, `server_*` tools are the default path. Use them for:

- model registration and instance lifecycle
- live telemetry reads and control writes
- diagnostics, communication inspection, and runtime scenarios

Treat `repo_*` tools as the persistence path when the user explicitly wants to
save a runtime-proven change back into the repository.

Protocol smoke tests are opt-in or failure-driven in `runtime_mcp`. Do not add
default Modbus, MQTT, OPC UA, or similar communication checks after an instance
already reached `RUNNING`, unless:

- the user explicitly asked for protocol proof
- the task is about register maps, bindings, or endpoints
- the instance failed to start and diagnostics are required

## Repository development workflow

Use this flow when the active work mode is `repo_dev`:

1. inspect and edit the repo as a normal development checkout
2. use `repo_*` tools and direct file edits for durable changes
3. update tests, catalogs, docs, packs, or installer assets when the change
   needs them
4. use MCP runtime tools only as supporting validation, not as a substitute for
   the repo change itself

`repo_dev` remains the default for ordinary manual clones, even if MCP is
available and a local `spx-server` is running.

Optional flags:

- `--read-only` to omit `--allow-write`
- `--server-name custom_name` to use a different MCP server id

The generated config prefers the local `.venv` Python interpreter when present
and otherwise falls back to `poetry run python -m spx_mcp ...`.

If you intentionally keep the repo in `--no-root` mode, use the module form:

```powershell
poetry run python -m spx_mcp list-tools
```

## Commands

List the available tools:

```powershell
poetry run spx-mcp list-tools
poetry run spx-mcp list-tools --allow-write
poetry run python -m spx_mcp list-tools
```

Check local prerequisites:

```powershell
poetry run spx-mcp doctor
poetry run spx-mcp doctor --json
poetry run python -m spx_mcp doctor
```

Run the MCP server over `stdio`:

```powershell
poetry run spx-mcp stdio
poetry run spx-mcp stdio --allow-write
poetry run python -m spx_mcp stdio
```

Run the live end-to-end smoke test against a local `spx-server`:

```powershell
C:\Python314\python.exe tools\mcp_live_smoke.py
```

This script launches `spx_mcp` over `stdio`, connects with an MCP client,
validates a catalog model, registers it on the running server, creates an
instance, inspects diagnostics, and exercises basic lifecycle operations.

## Tool groups

Read-only and diagnostics are always exposed:

- `repo_list_packs`
- `repo_list_profiles`
- `repo_find_models`
- `repo_get_model`
- `repo_validate_model`
- `repo_list_model_scenarios`
- `repo_get_model_scenario`
- `health`
- `server_list_models`
- `server_list_instances`
- `server_get_instance`
- `server_list_scenarios`
- `server_get_scenario`
- `server_get_attr`
- `server_get_attrs`
- `server_get_node`
- `server_get_logs`
- `server_get_communication`
- `server_get_bindings`
- `server_diagnose_instance`
- `server_list_connections`
- `server_get_connection`

Write tools are exposed only with `--allow-write`:

- `repo_upsert_model_scenario`
- `repo_delete_model_scenario`
- `server_register_model_from_catalog`
- `server_register_model_and_ensure_instance`
- `server_ensure_instance`
- `server_start_instance`
- `server_stop_instance`
- `server_reset_instance`
- `server_set_attr`
- `server_set_attrs`
- `server_ramp_attr`
- `server_upsert_scenario`
- `server_start_scenario`
- `server_stop_scenario`
- `server_delete_scenario`
- `server_upsert_connection`
- `server_delete_connection`
- `server_start_connections`
- `server_stop_connections`
- `server_start_connection`
- `server_stop_connection`
- `server_run_connection`
- `repo_bootstrap_pack`
- `repo_bootstrap_profile`

## Runtime Connection Workflow

Use runtime connections when a user asks for one instance attribute to influence,
feed, drive, or update another instance attribute. Typical requests include
"make weather brightness affect PV generation" or "send the HVAC load to the
main meter".

Recommended flow:

1. Use `server_list_instances` to find running instance keys.
2. Use `server_get_attrs` on the candidate source and target instances.
3. Choose a source telemetry or calculated output attribute.
4. Choose a target persistent input attribute, usually a `k__*` attribute.
5. Call `server_upsert_connection` with structured endpoint arguments.
6. Use `replace=true` for idempotent wiring and `start=true` for immediate use.
7. Call `server_start_connections` if the global `connections` container is not running.
8. Verify with `server_get_connection`; expect `state = RUNNING` and, when present, `propagation_status = ACTIVE`.
9. Change the source with `server_set_attr` or invoke `server_run_connection` once.
10. Read the target with `server_get_attrs` to confirm propagation.

Connection direction:

```text
from = source read endpoint = $out(source_instance.source_attr)
to   = target write endpoint = $in(target_instance.target_attr)
```

Prefer structured arguments over handwritten expressions:

```text
server_upsert_connection(
  connection_name="Weather_Brightness_to_PV_Physics_Illuminance",
  source_instance_key="Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT",
  source_attr_path="k__brightness_lux",
  target_instance_key="PV_Physics_Lux",
  target_attr_path="k__illuminance_lux",
  replace=true,
  start=true
)
```

Common smart-building patterns:

```text
Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT.k__brightness_lux
  -> PV_Physics_Lux.k__illuminance_lux

Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT.k__outdoor_temperature_c
  -> Building_Physics.k__outdoor_temperature_c

PV_Physics_Lux.pv_available_power_w
  -> Victron_Cerbo_GX_ESS_Modbus.pv_available_power_w

HVAC_Flexit_Nordic_BACnet.heating_coil_electric_power_kw
  -> Building_Energy_Aggregator.k__hvac_load_kw
```

After importing a system configuration, connections may exist but still be
`INITIALIZED`. Always inspect and start them before testing:

```text
server_list_connections()
server_get_connection(connection_name="...")
server_start_connections()
server_run_connection(connection_name="...")
```

## Notes

- The MCP tool reuses `spx_python` as the primary operational layer.
- Repository-specific glue is limited to catalog lookup, model validation, and
  convenience bootstrap flows.
- For runtime diagnostics, the tool can inspect generic tree paths, instance logs,
  communication blocks, and bindings.
- `server_get_attr` and `server_get_attrs` default to reading `external_value`;
  pass an explicit `.../internal_value` path only when you intentionally need an
  internal read target.
- For attribute-heavy flows, prefer `server_get_attrs` and `server_set_attrs` to
  reduce round trips and stdio/session overhead.
- `server_set_attr` and `server_set_attrs` default to writing `internal_value`;
  pass an explicit `.../external_value` path only when you intentionally need an
  external write target.
- `server_ramp_attr` ramps one numeric attribute from its current value (or an
  explicit `start_value`) to a target over `duration_s` and `steps`.
- `server_upsert_scenario` accepts the raw SPX scenario DSL mapping and injects it
  into `instance.scenarios` at runtime; use it for timed actions, conditions,
  alarms, or multi-step sequences that should execute on the SPX server itself.
- `server_start_scenario`, `server_stop_scenario`, and `server_delete_scenario`
  manage the runtime lifecycle of those injected scenarios.
- `repo_list_model_scenarios` and `repo_get_model_scenario` inspect scenario
  definitions stored in the catalog model YAML.
- `repo_upsert_model_scenario` and `repo_delete_model_scenario` persist scenario
  definitions into the catalog model file itself; after using them, re-register the
  model with `server_register_model_from_catalog` and recreate affected instances
  if you want the running server to pick up the change.
- `server_register_model_and_ensure_instance` is the convenience workflow for
  "register this catalog model on the server and give me one instance from it"
  in a single MCP call.
- `server_upsert_connection` creates or replaces one runtime connection. It can
  accept explicit `from_expr` / `to_expr`, but agents should prefer
  `source_instance_key`, `source_attr_path`, `target_instance_key`, and
  `target_attr_path` for ordinary wiring.
- `server_start_connections` starts the global connections container. Use it
  after imports, restores, or batch connection creation when the container is
  still `INITIALIZED`.
- `server_run_connection` executes one connection once and is useful for
  immediate verification before waiting for a source change hook.
- Runtime semantics matter:
  - scenario `overrides` behave like a temporary overlay and revert on `stop()`
  - scenario `actions` such as `function` or `set` materialize state changes and
    the resulting values remain after `stop()`
