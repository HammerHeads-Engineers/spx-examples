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
Use this path when the model is being created only for local MCP usage and live `spx-server` runtime validation, with no request for repo hardening or automated test coverage.
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
   4. verify protocol read of key telemetry
   5. verify protocol write of the main control input
   6. verify the mode or command path if it was implemented
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
- Bootstrap the repo-local Codex MCP config before first use or after interpreter changes:
  - Windows: `powershell -ExecutionPolicy Bypass -File tools\setup_codex_mcp.ps1`
  - Linux/macOS: `sh tools/setup_codex_mcp.sh`
- After creating or updating `.codex/config.toml`, restart Codex or open a fresh thread in this workspace before relying on MCP tools.
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
- [ ] Key telemetry is verified by protocol read
- [ ] Live control path works, for example setpoint write or protocol write updates runtime state

## Rules
- Backward compatibility: avoid renaming or removing existing model IDs, paths, or public APIs.
- Naming: `lower_snake_case` file names; for new or updated models keep `name` aligned with the file stem; use `__protocol` suffix when applicable.
- Release policy: for PRs targeting `develop`/`main`, use a Conventional Commit PR title (`type(scope): subject`).
- Release policy: to trigger Semantic Release version bumps, use releasable types in PR titles/merge commits (`feat:`, `fix:`, `perf:`) or include `BREAKING CHANGE:` in body/footer.
- Merge policy (recommended): prefer **Squash and merge** so the Conventional PR title becomes the commit message on `develop`/`main`.
- Do: reuse existing examples, keep YAML indentation at 2 spaces, keep changes additive.
- Do not: add pack-local model YAML files under `library/industries/<pack>/`.
- Do not: change runtime behavior unless required for tooling or validation.
