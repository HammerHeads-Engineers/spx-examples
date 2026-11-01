# Model-contribution automation

This procedure applies to an automation whose primary task is generating a new
device model and a durable contribution. Other tasks follow [AGENTS.md](../AGENTS.md)
and [CONTRIBUTING.md](../CONTRIBUTING.md); live experiments use the
[runtime workflow](RUNTIME_WORKFLOW.md).

## Inputs and deduplication

Require an objective, acceptance criteria, domain/pack, protocol and first-party
vendor references where relevant. Start from a behavioral twin under the
[authoring rules](LLM_SPEC.md).

Use the canonical repository's `develop` branch for candidate discovery and replay
checks. Absence on `main` does not imply a missing model. In a canonical checkout:

```sh
git fetch origin develop
poetry run python tools/check_model_branch_guard.py --base-ref origin/develop
```

For a fork, fetch canonical `upstream/develop` and supply that as `--base-ref`.
Re-run the guard on the automation branch before generating or editing YAML.
Reconcile duplicate/replay drift before continuing. The legacy
`automation/model-yaml` branch additionally requires `SPX_ALLOW_EXISTING_MODEL_EDITS=1`
and a rationale before modifying an existing model; the guard enforces that policy.

## Implementation and evidence

Follow the shared contribution flow. Preserve model IDs/paths/public behavior
unless the requested change explicitly requires a compatible migration. Register
pack membership in the catalog; update a profile when its runnable example changes.
Add `default_instances` / `start_instances` only when intentional sample provisioning
is part of the change. Run `poetry run python -m tools.catalog refresh`.

For each new model, provide meaningful runtime smoke coverage: load/register,
create/reset/start to `RUNNING`, verify the requested behavior, and clean up its
owned objects. Protocol changes also need at least a relevant read/write probe.
Use the target pack's integration suite, or `tests/core/runtime/` for a shared
protocol-free model. Record the actual tested server version and unavailable checks.

```sh
poetry run python -m tools.check --base-ref origin/develop
poetry run python -m tools.check --json --report dist/contribution-checks.json
```

Use the fork base reference when applicable. Execute the focused runtime test
only in an explicitly selected test environment with credentials supplied locally.
Public fork CI remains credential-free; it does not establish runtime qualification.
Trusted release CI tests the candidate artifact on disposable servers later.

The branch guard and its unit tests are maintained in this repository. Do not
assume a green public check has executed every pack integration test. Changes to
automation enforcement itself need tests demonstrating the claimed guard behavior.

## PR and CI remediation

Open/update a PR to `develop` with a Conventional Commit title, source links,
behavior/register rationale and actual validation evidence. Never target `main`
directly from model-generation automation. Maintainers review qualification and
promote releases through [the release workflow](CATALOG_RELEASES.md).

Monitor the branch CI after pushing. Fix the failing implementation on the same
branch and rerun the relevant checks. For a scheduled/unattended model-generation
automation, limit the automatic CI remediation loop to three consecutive failed
attempts. Then report branch/commit, workflow/job URLs, error signature, attempted
fixes and the next action. When that automation explicitly authorizes issue
creation, preserve the report in an issue; otherwise return it to its owner.

Keep task prompts short: objective, device, sources, constraints and acceptance
criteria. Link this procedure and the shared standards instead of copying them.
