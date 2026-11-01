# Documentation map

Use this repository to find, run and contribute SPX models. People and agents use
the same model standards and evidence; agents additionally follow the task-routing
and stopping rules in [AGENTS.md](../AGENTS.md).

## Choose a route

| You want to | Read in this order | Completion means |
| --- | --- | --- |
| Try a model | [Repository overview](../README.md) → [example quickstart](../examples/README.md) → a pack README | You can reproduce the expected result and identify its requirements |
| Work on a live server | [Runtime workflow](RUNTIME_WORKFLOW.md) → the needed [MCP tool reference](MCP.md) | The requested instance, scenario or connection works on that server |
| Contribute to the library | [Contributing](../CONTRIBUTING.md) → [authoring rules](LLM_SPEC.md) → relevant [language reference](MODEL_LANGUAGE.md) | A reviewable PR with actual validation evidence |
| Automate model contributions | The contribution route → [automation workflow](AUTOMATION.md) | A deduplicated contribution PR with CI results and explicit runtime limits |
| Consume catalogs | [Catalog contract](CATALOG_CONTRACT.md) | A verified compatible catalog pinned to an immutable revision |
| Publish a catalog | [Release operations](CATALOG_RELEASES.md) | Public artifacts and qualification evidence match the candidate |

The live-server route does not automatically create a community contribution.
Publishing a catalog does not update existing installations or live instances.

## Which source owns the answer?

| Question | Authority |
| --- | --- |
| Product installation, UI usage, language/API semantics | [SPX product documentation](https://docs.simplephysx.com) maintained in `spx-docs` |
| Offline model language and MCP reference | Generated [MODEL_LANGUAGE.md](MODEL_LANGUAGE.md) and [MCP.md](MCP.md), pinned by [docs-source.json](../docs-source.json) |
| Library conventions: names, units, model adaptation | [LLM_SPEC.md](LLM_SPEC.md), for both humans and agents |
| Fork, checks, PR review and evidence | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Agent routing and limits | [AGENTS.md](../AGENTS.md); detailed live work in [RUNTIME_WORKFLOW.md](RUNTIME_WORKFLOW.md) |
| Model IDs, paths, membership and defaults | [Source catalogs](../library/catalog/) |
| A released catalog's contents and tested targets | Its `catalog.json`, `release.json` and qualification assets in [GitHub Releases](https://github.com/HammerHeads-Engineers/spx-examples/releases) |
| Product/MCP installation, client setup, packaging and signing | Private `spx-installer`; follow the public product installation guide as a user |

Propose product-semantic corrections in `spx-docs`. The two generated offline
references are updated through the docs-sync PR workflow; do not hand-edit them.
An older reference example does not override current repository conventions.

## Understand versions and evidence

| Value | What it versions |
| --- | --- |
| Catalog version, e.g. `2026.11.01.1` | An immutable library artifact, independent of product release numbers |
| Catalog schema, currently `1` | The discovery/manifest format understood by catalog consumers |
| `server_compatibility` and `qualification_targets` | Declared server support and exact versions that release CI must test |
| SPX Server version | The runtime actually executing the models |
| Python package / MCP version | The client or local tool implementation |
| Installer version | Product installation and deployment tooling |
| `docs-source.json` commit | The product-reference snapshot used in this checkout |

The offline reference's baseline and a catalog's qualified runtime version can
differ. Consult the release report for proof of a particular catalog/server pair;
do not infer support from a similar version number or from successful YAML parsing.
Lifecycle tests establish registration/start/cycles/restart/cleanup. A protocol
read/write test proves a narrower transport behavior. Device fidelity requires
its own model-specific evidence.

## Targeted and historical notes

[RELEASE_MODEL_QA.md](RELEASE_MODEL_QA.md) preserves behavior and protocol notes for
a historical installer-selected subset. It is not a qualification report for the
current whole catalog; follow the linked release evidence for that purpose.

The [emSign remediation plan](EMSIGN_6424.md) and [results](EMSIGN_6424_RESULTS.md)
are historical records dated October 2026. Their paths and commands describe the
environment at that time, including private installer/server work. Use current
product instructions for operational changes.

## Keep these guides usable

Run `poetry run python -m tools.check` before submitting a documentation change.
It checks local link targets, referenced repository Python commands and explicitly
marked complete model examples, alongside the model/catalog/unit checks. External
websites, Markdown anchors, notebooks and live runtime behavior need separate
review or execution; this check does not claim to verify them.
