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

## How to add a model
1. Copy the closest existing model YAML in `library/domains/...`.
2. Review the pack spec in `library/industries/<pack>/SPEC.md` if the model belongs to a pack.
3. Name the file `lower_snake_case` with optional `__protocol` suffix; for new or updated models, keep `name` aligned with the file stem.
4. For new or updated models, include `name`, `description`, and `attributes` when feasible (legacy models may omit `name`/`description`).
5. Update `library/catalog/models.yaml` with the new entry, including `domain_group`, `device_class`, and `vendor`.
6. If you add a new domain or protocol, update `library/catalog/domains.yaml` or `library/catalog/services.yaml`.
7. If the model belongs to a pack, update `library/catalog/industries.yaml`, relevant `profiles/<pack>/*.yaml`, the pack README in `library/industries/<pack>/README.md`, and regenerate `library/industries/<pack>/MODELS.yaml` via `poetry run python tools/render_pack_indexes.py`.
8. Add or update tests under `tests/` (use existing pack tests as templates).

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

## Rules
- Backward compatibility: avoid renaming or removing existing model IDs, paths, or public APIs.
- Naming: `lower_snake_case` file names; for new or updated models keep `name` aligned with the file stem; use `__protocol` suffix when applicable.
- Release policy: for PRs targeting `develop`/`main`, use a Conventional Commit PR title (`type(scope): subject`).
- Release policy: to trigger Semantic Release version bumps, use releasable types in PR titles/merge commits (`feat:`, `fix:`, `perf:`) or include `BREAKING CHANGE:` in body/footer.
- Merge policy (recommended): prefer **Squash and merge** so the Conventional PR title becomes the commit message on `develop`/`main`.
- Do: reuse existing examples, keep YAML indentation at 2 spaces, keep changes additive.
- Do not: add pack-local model YAML files under `library/industries/<pack>/`.
- Do not: change runtime behavior unless required for tooling or validation.
