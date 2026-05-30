# AGENTS.md

This file is the entry point for automated agents and contributors.

## Repository map
- Models: `library/domains/<domain_group>/<device_class>/<vendor|generic>/*.yaml`
- Catalogs: `library/catalog/*.yaml`
- Packs: `library/industries/<pack>/{README.md,SPEC.md,MODELS.yaml}` and `profiles/<pack>/`
- Tests: `tests/` (pack tests in `tests/packs/<pack>/`)
- Examples: `examples/` (not used by validation)

Catalog taxonomy is the source of truth for pack membership and higher-level grouping:
- `domain_group`: one of `building`, `environment`, `industrial`, `energy`, `lab`
- `device_class`: lower_snake_case functional class such as `sensor`, `controller`, `meter`
- `vendor`: lower_snake_case vendor slug or `generic`

## Attribute naming standard
Apply this standard to every new or updated model YAML. Legacy models may still deviate, but cleanup work should move them toward this shape.

- Use `lower_snake_case` for all attribute names.
- Split attributes into four semantic groups:
  - `k__*`: primary control inputs and simulation-critical state written by users, protocols, or higher-level control logic. Use for setpoints, targets, modes, enable/disable flags, and other values that directly drive behavior.
  - `cmd__*`: command/trigger inputs. Use for one-shot actions, trigger flags, start/stop requests, open/close requests, pause/resume commands, and similar control edges.
  - plain attributes without prefix: normal telemetry, measurements, derived values, diagnostics, counters, status readbacks, and other ordinary runtime state.
  - `_helper` / leading `_`: internal helper attributes that support model logic and should not be treated as public-facing state.
- Do not use `k__` for derived/calculated values, pure telemetry, diagnostics, or helper state.
- There is no separate dedicated prefix for "ordinary" attributes. If an attribute is neither key control state nor command/trigger input nor hidden helper state, keep it as plain `lower_snake_case`.
- Prefer explicit units in attribute names via suffixes when the quantity is dimensional, for example:
  - `_c`, `_pct`, `_ms`, `_s`, `_hz`, `_khz`, `_v`, `_a`, `_ma`, `_w`, `_kw`, `_wh`, `_kwh`, `_va`, `_kva`, `_var`, `_bar`, `_mbar`, `_ppm`, `_nm`, `_nm_s`, `_sccm`
- For new or updated typed attributes, prefer the structured form:
  - `type`
  - `default`
  - `unit` when applicable
- Keep the unit suffix in the attribute name and the explicit `unit:` field aligned when both are present, for example `pressure_mbar` with `unit: mbar`, `temperature_c` with `unit: degC`, `energy_total_kwh` with `unit: kWh` or repo-consistent equivalent.
- When deciding between `k__*` and `cmd__*`:
  - use `k__*` for persistent control state that can be read back as the current target or mode
  - use `cmd__*` for command-style inputs that represent an action or trigger rather than steady state
- For compatibility work on existing models, preserve legacy public names only when backward compatibility is required; otherwise prefer this standard.
- Reference docs for deeper rationale: `docs/LLM_SPEC.md` and `docs/MODEL_LANGUAGE.md`.

## Model docs to read first
`AGENTS.md` contains the minimum mandatory operating rules, but it is not the full modeling spec.

- When creating, renaming, or substantially updating model YAML files, always read `docs/LLM_SPEC.md` and `docs/MODEL_LANGUAGE.md` before editing.
- Treat `docs/LLM_SPEC.md` as the repo-level modeling playbook for naming, `k__` vs `cmd__` decisions, golden/reference models, and expected PR summary context.
- Treat `docs/MODEL_LANGUAGE.md` as the source of truth for the YAML modeling language structure and supported constructs.
- If there is any conflict between an older model example and these docs, prefer the docs for new work, unless backward compatibility requires preserving the legacy shape.
- Do not assume that examples alone define the standard; check the docs explicitly.

## Mode Resolution
Resolve the active work mode in this order:

1. explicit user intent in the current request
2. `.spx/workspace_mode.toml` when it exists
3. legacy `.codex/workspace_mode.toml` when it exists
4. `.spx-mcp-workspace.json` workspace metadata
5. default to `repo_dev`

Do not infer the work mode from MCP availability, a running `spx-server`, or the mere presence of local runtime files. A full repo checkout can still be doing MCP-driven live work, and a packaged runtime workspace is not a normal development checkout.

The technical workspace kind is separate from the semantic work mode:

- installer-managed workspaces are meant for `runtime_mcp`
- full git checkouts are meant for `repo_dev`

### `runtime_mcp`
- MCP-first, shortest path to the requested live result
- do not add repo tests, pack updates, catalog expansions, or doc updates unless the user explicitly asks for persistence or release-grade work
- prefer local validation against the running server over repo-wide hardening
- runtime changes are ephemeral unless the user explicitly asks to persist them back into the repository

#### `runtime_mcp` model work
- use the smallest repo touch set needed to make the live runtime result work
- update model YAML only when the runtime flow truly depends on it
- do not default to catalog, profile, pack, README, or pytest work unless the user explicitly asks for a persistent repo change

#### `runtime_mcp` instance work
- prefer MCP `server_*` tools for register, ensure, recreate, start, stop, reset, and live validation flows
- optimize for a working live instance quickly instead of polishing repo structure
- if the user asks only for runtime behavior on an existing instance, do not turn that into repo development by default
- for model-and-instance tasks, default success means: model is valid enough for runtime use, registered on the live server, instance exists, and instance state is `RUNNING`
- once the instance is `RUNNING`, stop unless the user explicitly asks for protocol verification, deeper diagnostics, or persistence back into the repository

#### `runtime_mcp` diagnostics and scenario flows
- use `server_get_*`, `server_set_*`, `server_ramp_attr`, and runtime scenario tools as the default path for live diagnostics and control work
- prefer the shortest runtime path that proves telemetry, control, or scenario behavior on the running server
- persist runtime scenarios or attribute behavior back into the repo only when the user explicitly asks for that promotion
- protocol smoke tests such as Modbus/MQTT/OPC UA read-write checks are opt-in or failure-driven, not part of the default success path

#### `runtime_mcp` connections work
- Treat user requests such as "make X affect Y", "connect A to B", "feed A into B", or "wire this measurement into that model" as runtime connection tasks unless the user explicitly asks for model YAML changes.
- Prefer the MCP connection tools over direct API calls: `server_list_connections`, `server_get_connection`, `server_upsert_connection`, `server_delete_connection`, `server_start_connections`, `server_start_connection`, and `server_run_connection`.
- Use `server_list_instances`, `server_get_instance`, and `server_get_attrs` to identify exact instance keys and attribute names before creating a connection.
- Direction matters: `from` is the source read endpoint and becomes `$out(source_instance.source_attr)`; `to` is the target write endpoint and becomes `$in(target_instance.target_attr)`.
- Prefer telemetry or calculated outputs as sources, for example `brightness_lux`, `pv_available_power_w`, or `heating_coil_electric_power_kw`.
- Prefer persistent control or simulation inputs as targets, usually `k__*` attributes such as `k__illuminance_lux`, `k__outdoor_temperature_c`, or `k__hvac_load_kw`.
- Do not use `cmd__*` as a target for continuous propagation unless the requested behavior is explicitly a command or one-shot trigger.
- For `server_upsert_connection`, prefer structured endpoint arguments (`source_instance_key`, `source_attr_path`, `target_instance_key`, `target_attr_path`) over handwritten expressions. Use `from_expr` and `to_expr` only when a custom expression is required.
- Set `replace=true` for idempotent user-requested wiring. Set `start=true` when creating the connection, then call `server_start_connections` if the global `connections` container is not running.
- After import or restore, always check `server_list_connections` and `server_get_connection`. If a connection or the container is `INITIALIZED`, start it before testing propagation.
- Success for runtime connection work means the connection exists, is `RUNNING`, reports `propagation_status = ACTIVE` when available, and a source value change or `server_run_connection` updates the target.

### `repo_dev`
- use the normal repository development workflow
- update code, models, catalogs, tests, docs, packs, and installer assets as needed for a durable repo change
- run the relevant validation for the touched area instead of stopping at local runtime proof

## How to add a model
1. Copy the closest existing model YAML in `library/domains/...`.
2. Review the pack spec in `library/industries/<pack>/SPEC.md` if the model belongs to a pack.
3. Name the file `lower_snake_case` with optional `__protocol` suffix; for new or updated models, keep `name` aligned with the file stem.
4. For new or updated models, include `name`, `description`, and `attributes` when feasible (legacy models may omit `name`/`description`).
5. Update `library/catalog/models.yaml` with the new entry, including `domain_group`, `device_class`, and `vendor`.
6. If you add a new domain or protocol, update `library/catalog/domains.yaml` or `library/catalog/services.yaml`.
7. If the model belongs to a pack, update `library/catalog/industries.yaml`, relevant `profiles/<pack>/*.yaml`, the pack README in `library/industries/<pack>/README.md`, and regenerate `library/industries/<pack>/MODELS.yaml` via `poetry run python tools/render_pack_indexes.py`.
8. Add or update tests under `tests/` (use existing pack tests as templates).

## Fast path for MCP-only models
Use this path when the active work mode is `runtime_mcp`, or when the model is being created only for local MCP usage and live `spx-server` runtime validation with no request for repo hardening or automated test coverage.
If the user asks for a new local SPX model from a vendor manual and does not explicitly ask for release hardening, automated tests, or pack-wide integration, default to this path immediately.
Do not spend time debating between the full repo flow and the MCP-only flow when the task is clearly local runtime validation.

1. Start from the closest existing runtime model and preserve its physics, actions, scenarios, and attribute structure unless the new device strictly requires a different behavior model.
   For single-loop thermal controllers and similar devices, start from the nearest existing controller twin and adapt it instead of re-modeling behavior from scratch.
2. Prefer vendor adaptation over full re-modeling:
   - keep the nearest behavioral twin as-is
   - change only metadata, naming, descriptions, protocol mapping, register map, and the minimum vendor-specific attributes needed for communication
3. For Modbus devices, treat the manual as a source for the minimal useful register subset first:
   - PV / measured value
   - SP / target setpoint
   - MV / output or manual output
   - mode / run-stop / auto-manual when available
   - minimal status only if needed for live validation
   - the smallest extra subset needed for the requested scenario or demo
   Avoid broad PDF exploration and avoid implementing a full register map unless the user explicitly asks for it.
4. If the real protocol exposes command semantics that the SPX runtime does not support 1:1, implement the smallest runtime-compatible bridge that preserves the live control path and document that choice in the model description.
5. Do not add unit tests or pytest coverage by default for this fast path.
6. For local live validation, prefer the simplest reliable registration/bootstrap path.
   If high-level helpers depend on optional modules or fail due to environment issues, fall back quickly to direct client or API registration instead of debugging helper internals.
7. Run live validation early, in this order:
   1. `tools/validate_models.py`
   2. register the model on the local SPX server
   3. recreate and start the instance
   4. stop when the instance reaches `RUNNING`, unless the user explicitly asked for protocol verification
   5. verify protocol read of key telemetry only when the task asks for communication proof or when runtime behavior is still unclear
   6. verify protocol write or mode-command paths only when the task explicitly asks for it or when startup/behavior is failing
8. When checking live instances, do not assume runtime tree shape blindly.
   If the runtime object layout is unclear, inspect the live instance document or validate through protocol reads and writes instead of spending time on guessed attribute paths.
9. If live MCP validation passes, stop there unless the user explicitly asks for tests, broader pack integration, or release-grade hardening.

Preferred order of work for this fast path:
- inspect the closest existing model
- extract only the needed register table rows from the vendor manual
- clone and minimally adapt the model YAML
- update catalog and pack metadata only if needed for MCP discovery
- validate and register early instead of doing long speculative refinement
- recreate instance, start instance, verify protocol read/write, then verify any mode or command path

For thermal controllers and similar single-loop devices, prefer using an existing controller twin such as Eurotherm as the behavioral template and swapping only the communication layer unless the user explicitly asks for vendor-specific control physics.

## Runtime-only operations
When the user is clearly asking for runtime-only work on a live server, stay in `runtime_mcp` unless they explicitly ask for persistence into the repository.

- existing instance tuning, diagnostics, and command-path checks should stay MCP-first
- scenario injection, attribute ramps, and live control experiments should stay runtime-local by default
- do not introduce repo edits just because a runtime-only request happened inside a repo checkout

## How to add a pack
1. Create `library/industries/<pack>/README.md` and `profiles/<pack>/`.
2. Add the pack to `library/catalog/industries.yaml`.
3. Add model entries to `library/catalog/models.yaml` and include the pack in `packages`.
4. Add pack tests under `tests/packs/<pack>/`.

## How to add tests
- Use pytest under `tests/` and follow existing fixtures in `tests/conftest.py`.
- Pack-specific integration tests live in `tests/packs/<pack>/integration/`.
- For tests that use the `spx_python` client, follow `SPX_PYTHON_LLM.md` (the single source of truth shipped with the spx-python package).

## Local validation and tests
```bash
poetry install --with dev --no-root
poetry run python tools/check_model_branch_guard.py --base-ref origin/develop
poetry run python tools/render_pack_indexes.py
poetry run python tools/validate_models.py
poetry run pytest
```

## Local MCP tool
- Repo-local MCP entrypoint: `poetry run python -m spx_mcp ...`
- Installed script entrypoint: `poetry run spx-mcp ...` after `poetry install --with dev`
- Use the MCP tool for repo-aware catalog inspection, model validation, and live `spx-server` diagnostics when the task involves local runtime investigation.
- Bootstrap the repo-local Codex MCP config before first use with Codex or after interpreter changes:
  - Windows: `powershell -ExecutionPolicy Bypass -File tools\setup_codex_mcp.ps1`
  - Linux/macOS: `sh tools/setup_codex_mcp.sh`
- After creating or updating `.codex/config.toml`, restart Codex or open a fresh thread in this workspace before relying on MCP tools.
- Claude Code uses project-local `.mcp.json`; packaged MCP workspaces generate it automatically next to `CLAUDE.md`, which points Claude Code at `AGENTS.md`.
- When the host client already exposes the repo-local MCP server, prefer host-managed MCP tools over ad hoc shell calls or custom Python MCP client scripts.
- Do not launch `python -m spx_mcp stdio` from the shell for routine read/write flows; reserve direct CLI use for bootstrap, `doctor`, `list-tools`, smoke tests, or MCP debugging.
- Assume `stdio` session reuse only within the current host-managed session; do not rely on transport persistence across separate threads.
- Prefer fewer, higher-level MCP calls over many small calls to reduce handshake and round-trip overhead.

Pack tests (require `SPX_PRODUCT_KEY` and a running stack):
```bash
poetry run pytest tests/packs/<pack>
```

## Definition of Done
- [ ] Model YAML or profile added/updated
- [ ] Catalogs updated (`library/catalog/*.yaml`)
- [ ] Pack docs updated when applicable
- [ ] Tests added or updated
- [ ] `tools/validate_models.py` passes
- [ ] `pytest` passes

### MCP-only Definition of Done
- [ ] Model YAML added or updated
- [ ] Catalog updated if MCP discovery requires it
- [ ] `tools/validate_models.py` passes
- [ ] Model registers on the local SPX server
- [ ] Instance is recreated from the updated model and starts successfully
- [ ] Final runtime result reports model id, instance key, state, and any endpoint details needed for the current task

Protocol verification is not part of the default `runtime_mcp` definition of done. Add protocol reads/writes only when the user explicitly asks for communication proof or when failure-driven diagnostics require it.

## Rules
- Backward compatibility: avoid renaming or removing existing model IDs, paths, or public APIs.
- Naming: `lower_snake_case` file names; for new or updated models keep `name` aligned with the file stem; use `__protocol` suffix when applicable.
- Release policy: for PRs targeting `develop`/`main`, use a Conventional Commit PR title (`type(scope): subject`).
- Release policy: to trigger Semantic Release version bumps, use releasable types in PR titles/merge commits (`feat:`, `fix:`, `perf:`) or include `BREAKING CHANGE:` in body/footer.
- Merge policy (recommended): prefer **Squash and merge** so the Conventional PR title becomes the commit message on `develop`/`main`.
- Do: reuse existing examples, keep YAML indentation at 2 spaces, keep changes additive.
- Do not: add pack-local model YAML files under `library/industries/<pack>/`.
- Do not: change runtime behavior unless required for tooling or validation.
