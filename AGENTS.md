# Agent working rules

Help the user reach a verifiable result using the same model, compatibility and
review standards as human contributors. [README.md](README.md) is the entry point;
[docs/README.md](docs/README.md) maps the task guides. `CLAUDE.md` imports this file.

## 1. Resolve the task mode

Resolve mode in this order:

1. Explicit user intent in the current request.
2. `.spx/workspace_mode.toml`.
3. Legacy `.codex/workspace_mode.toml`.
4. `.spx-mcp-workspace.json` workspace metadata.
5. Default to `repo_dev`.

MCP availability, a running server and local runtime files do not select the mode.
A full checkout normally supports `repo_dev`; installer-managed workspaces normally
support `runtime_mcp`. The user's semantic task still takes precedence.

| Mode | Work and stopping rule |
| --- | --- |
| `runtime_mcp` | Use MCP to achieve the requested live result. Model/instance work normally ends at `RUNNING`; connections additionally need demonstrated propagation. Follow [runtime rules](docs/RUNTIME_WORKFLOW.md). |
| `repo_dev` | Make a durable library/tooling change, validate the touched area and provide a reviewable diff/PR. Follow [CONTRIBUTING.md](CONTRIBUTING.md). |

For local model creation from a vendor manual, default to the runtime fast path
unless the user asks for a persistent contribution or release-grade work. Do not
add catalogs, pack docs or pytest work to a runtime experiment unless required for
discovery or explicitly requested. Promote runtime work to the repository only
when the user requests persistence.

## 2. Read the authority for this task

| Task | Required reading |
| --- | --- |
| Create, rename or substantially update model YAML | [Model authoring rules](docs/LLM_SPEC.md) and [model-language reference](docs/MODEL_LANGUAGE.md); the target pack's `SPEC.md` when relevant |
| Instances, diagnostics, scenarios or connections | [Runtime workflow](docs/RUNTIME_WORKFLOW.md); [MCP reference](docs/MCP.md) for exact tools |
| Catalog compatibility, resources, deprecation or channel policy | [Catalog contract](docs/CATALOG_CONTRACT.md) |
| Contribution tests and PRs | [CONTRIBUTING.md](CONTRIBUTING.md); [task template](docs/LLM_TASK_TEMPLATE.md) when useful |
| New-model generation automation | [Automation workflow](docs/AUTOMATION.md), in addition to the contribution rules |
| Catalog publication | [Release operations](docs/CATALOG_RELEASES.md) |

`spx-docs` owns product/language semantics. `docs/MODEL_LANGUAGE.md` and `docs/MCP.md`
are generated offline snapshots pinned by `docs-source.json`: never hand-edit them.
Propose semantic corrections upstream. These local task guides own repository
conventions. If an older model conflicts with the current rules, follow the rules
for new work while preserving required public compatibility.

## 3. Preserve these invariants

- Keep existing model IDs, paths and public attributes/APIs stable. Use explicit
  deprecation/migration for maintained lines; never silently replace a published model.
- Reuse the closest behavioral twin. Preserve its physics/actions/scenarios when
  adapting a vendor protocol unless the task requires a behavior change.
- New/updated YAML uses 2-space indentation, `lower_snake_case` file/name fields,
  `k__*` persistent controls, `cmd__*` triggers, plain telemetry and `_` helpers.
  Follow the [authoring rules](docs/LLM_SPEC.md) for units and identifiers.
- Parameterize configurable communication endpoints and instance identifiers with
  `meta_parameters` and `$param(...)`; keep simulation tuning in attributes.
  Supported bindings need explicit stable names. Audit siblings when fixing a
  shared transport issue and preserve legacy public interfaces where required.
- Put model YAML under `library/domains/`, membership in `library/catalog/`, and
  declared helpers in `extensions/` or `library/assets/`. Never add pack-local model
  YAML under `library/industries/` or edit generated indexes by hand.
- Compatibility declarations need actual evidence. Static validation, `RUNNING`,
  protocol interoperability and physical fidelity are separate claims. State what
  was tested and mark unavailable checks unverified.
- BLE examples remain preview-only until separate BLE QA. A skipped/excluded model
  is never a passing stable qualification; every model in a stable artifact must
  be covered on its declared targets.
- Keep keys, private endpoints and personal runtime state out of committed files,
  reports and PR text. Use environment configuration for credentials.
- Product/MCP installation, Python bootstrap, client setup, native packaging,
  signing and product releases belong to private `spx-installer`. This public
  repository owns model/example/MCP runtime content and model-only catalog releases.
  Do not add installer code or older-installer compatibility shims here.

## 4. Use the right tools and checks

Prefer host-managed MCP tools for catalog inspection and live-server work when
available. Do not run `python -m spx_mcp stdio` as an ad hoc shell client; reserve
direct CLI calls for `doctor`, `list-tools`, bootstrap or MCP debugging. Do not
assume stdio sessions persist across chats. The independent-checkout launch shape
and installed SDK guide location are in [the example guide](examples/README.md).

For a persistent contribution, use Python 3.12 / Poetry 2.2.1:

```sh
poetry install --with dev
poetry run python -m tools.catalog refresh
poetry run python -m tools.check --base-ref origin/develop
```

Use `--json --report dist/contribution-checks.json` for machine-readable evidence.
For a fork, use canonical `upstream/develop` as the base reference, as described
in CONTRIBUTING; `origin/develop` above assumes a canonical maintainer checkout.
`--no-tests` is structural iteration only. Public PR CI supplies the exact PR base
SHA; runtime integration checks require an explicitly selected test environment.
Follow [CONTRIBUTING.md](CONTRIBUTING.md) for meaningful tests and scoped execution.

## 5. Report completion accurately

For `runtime_mcp`, report the requested result, model ID, instance key/state and
needed endpoint details. Connection work also reports state and propagation proof.
Stop at that result unless deeper testing was requested or a failure needs diagnosis.

For `repo_dev`, report purpose, changed model IDs/files, check results and limitations.
Target contribution PRs at `develop` with a Conventional Commit title. Prefer squash
for contributions; preserve ancestry when promoting `develop` to `main`. Publication
follows the separate release workflow and requires its evidence gates. A passing
local check alone does not mean the change has been published or runtime-qualified.
