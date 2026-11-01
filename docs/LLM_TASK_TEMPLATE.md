# LLM Task Template

Use this template for persistent model contributions in `repo_dev` mode. For a
runtime-only request, follow the smaller `runtime_mcp` workflow in `AGENTS.md`.
Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and the [authoring rules](LLM_SPEC.md).
Read the [language reference](MODEL_LANGUAGE.md) before substantive YAML work.

## Goal
- What is the change and why?
- What are the explicit acceptance criteria?

## Inputs
- Target domain / pack:
- Target protocol:
- Required source constraints (if vendor/protocol-specific):
- Branch policy: contribution PR base is `develop`.
- Canonical base reference: `origin/develop` for a maintainer checkout or `upstream/develop` for a fork.

## Base example
- Closest existing model/profile/test used as a starting point:

## Plan (implementation)
1. 
2. 
3. 

## Files touched
- 

## Public contract and catalog
- Stable model ID and path; existing public attributes preserved:
- Catalog taxonomy and target pack membership in `packages`:
- Profile/example changes, only if the contribution changes a runnable example:
- Server compatibility and the evidence supporting any new claim:
- Explicit local Python/resource dependencies in `distribution.resources`:
- License and provenance of contributed content:
- Generated indexes refreshed with `poetry run python -m tools.catalog refresh`:

## Runtime smoke test plan (required for new model YAML)
- Model path:
- Target pack:
- Smoke test path:
- Bootstrap method (`spx_python` + instance start):
- Protocol probe(s), when relevant to the changed behavior:
- Expected running/healthy criteria:
- Cleanup method and isolated test environment:
- Actual tested server version; unavailable checks explicitly marked unverified:

## Validation
```bash
poetry run python -m tools.check --base-ref origin/develop
poetry run python -m tools.check --json --report dist/contribution-checks.json
```

The shared check runs structural validation, public-contract checks when a base
reference is supplied, documentation checks, catalog export verification, and unit suites.
Use `--base-ref upstream/develop` in the fork workflow from CONTRIBUTING.
Add behavior tests that prove the change; use
`templates/tests/test_temperature_behavior.py.example` as a runtime starting point.
`--no-tests` is a structural check only, not complete contribution validation.

## Failures and evidence
- Fix implementation and test failures before declaring completion.
- Record any external blocker, affected check, and the evidence collected.
- Never report an unavailable runtime or protocol test as passed.
- Do not include product keys, credentials, private endpoints, or raw secret-bearing logs.

## PR summary (target `develop`)
- Source links (first-party):
- Register/attribute rationale:
- `k__` / `cmd__` decisions:
- Validation/test evidence:

## Risks or follow-ups
- 
