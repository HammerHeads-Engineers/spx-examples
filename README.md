# spx-examples

Public SPX models, industry packs, runnable examples, runtime MCP modules and
agent working instructions. The full product documentation lives at
[docs.simplephysx.com](https://docs.simplephysx.com).

## Choose your next step

| I want to… | Start here |
| --- | --- |
| Work with an agent: choose live runtime or a durable contribution | [Agent Start Here](https://docs.simplephysx.com/llm-first-model-authoring/agent-start-here) |
| Install SPX | [Installation Guide](https://docs.simplephysx.com/readme/installation-guide) |
| Understand model definitions in YAML or JSON | [Model documentation](https://docs.simplephysx.com/reference/model-definition-reference), or [offline snapshot](docs/MODEL_LANGUAGE.md) |
| Find an existing model or industry pack | [Device Catalog](https://docs.simplephysx.com/usage-scenarios-and-examples/device-catalog), then `library/` below |
| Run my first simulation in the UI | [First device in the UI](https://docs.simplephysx.com/readme/getting-started) |
| Write a model in YAML or JSON | [Create your first model](https://docs.simplephysx.com/spx-development-guide/build-your-first-simulation) |
| Work with a live server through an agent | [MCP guide](https://docs.simplephysx.com/llm-first-model-authoring/connect-llm-with-spx-mcp), or [offline snapshot](docs/MCP.md) |
| Contribute a model, as a person or agent | [Contribution quickstart](CONTRIBUTING.md), [AGENTS.md](AGENTS.md), [task template](docs/LLM_TASK_TEMPLATE.md) |
| Build or consume a versioned model catalog | [Catalog contract](docs/CATALOG_CONTRACT.md), [release flow](docs/CATALOG_RELEASES.md) |

## Library overview

<!-- catalog-overview:start -->

97 catalog models across 5 domain groups.

| Domain group | Models |
| --- | ---: |
| `building` | 15 |
| `energy` | 25 |
| `environment` | 5 |
| `industrial` | 22 |
| `lab` | 30 |

Packs: [`smart_building_pack`](library/industries/smart_building_pack/README.md), [`energy_pack`](library/industries/energy_pack/README.md), [`embedded_lab_pack`](library/industries/embedded_lab_pack/README.md), [`industrial_iiot_pack`](library/industries/industrial_iiot_pack/README.md).

Protocol tags: `bacnet`, `ble`, `coap`, `http`, `knx`, `lwm2m`, `matter`, `modbus`, `mqtt`, `ocpp`, `opcua`, `scpi`.

These are reference simulations, not manufacturer-certified digital twins.
<!-- catalog-overview:end -->

The library advances independently of product installers. Public `catalog-*`
releases contain versioned discovery metadata, model/resource hashes and an
offline model archive. Preview and qualified stable releases follow the
[catalog release flow](docs/CATALOG_RELEASES.md). Existing installer builds still
use their pinned public context until their catalog consumer is updated;
updating this checkout does not update installed services or running instances.
Stable catalogs can contain fewer models than the source library when examples
are preview-only. BLE is currently deferred; CI tests all models published in the
stable artifact against declared server targets and probes latest official/RC
servers separately.

## Repository map

| Path | Contents |
| --- | --- |
| `library/domains/<domain_group>/<device_class>/<vendor>/` | Model YAML files |
| `library/catalog/` | Discovery, domain, pack and service metadata |
| `library/industries/` and `profiles/` | Pack instructions, indexes and presets |
| `examples/` and `extensions/` | Runnable scripts/notebooks and model helpers |
| `spx_mcp/` | Runtime MCP and catalog tools |
| `tests/` and `tools/` | Validation and contribution tooling |
| `schemas/` and `templates/` | Distribution contract, model starter and behavior-test template |
| `docs/` | Agent playbook plus generated offline product references |

## Minimal model: PT100-style temperature telemetry

Save this as `pt100_demo.yaml` while experimenting:

```yaml
name: pt100_demo
description: Minimal deterministic temperature sensor
attributes:
  k__temperature_c:
    type: float
    default: 20.0
    unit: degC
  temperature_c:
    type: float
    default: 20.0
    unit: degC
actions:
  - function: $in(temperature_c)
    name: update_temperature
    call: $in(k__temperature_c)
```

`k__temperature_c` is the persistent input; `temperature_c` is telemetry.
This is a temperature model, not a physical PT100 resistance calculation.
The [complete offline reference](docs/MODEL_LANGUAGE.md) provides equivalent
JSON and explains units, actions, scenarios, timers and parameterized
communication. The [portal model documentation](https://docs.simplephysx.com/reference/model-definition-reference)
is the stable online entry point. Library contributions use YAML and require a
catalog entry; JSON is supported at the API/import boundary.

## Development and validation

Use Python 3.12 (the CI baseline) and Poetry. MCP requires Python 3.10+.

```sh
poetry install --with dev
poetry run python -m tools.check
```

This is the same credential-free command used by public CI on Windows and Linux.
Use `--json --report dist/contribution-checks.json` for agents and `--no-tests`
only for fast structural iteration. See [CONTRIBUTING.md](CONTRIBUTING.md) for
the scaffold command, behavioral twins, generated-file refresh, testing and PR
review. A model/catalog draft and its derived indexes can be created together:

```sh
poetry run python -m tools.catalog scaffold --id Community.Pt100 --name community_pt100 --description "Temperature demo" --pack embedded_lab_pack
```

Static validation does not establish runtime compatibility. Stable catalog
publication requires reports from actual target servers, bound to the exact
catalog hash. Model-specific protocol proof remains part of transport changes.

For live work, set `SPX_BASE_URL` and `SPX_PRODUCT_KEY` locally; keep keys private.
Integration tests require the corresponding stack and services. Start the
installed environment with SPX Start before running the examples.

## Documentation ownership and updates

`spx-docs/main` owns product semantics. `docs/MODEL_LANGUAGE.md` and `docs/MCP.md`
are complete generated offline snapshots; [docs-source.json](docs-source.json)
records their exact source. Propose semantic corrections in `spx-docs`, not by
editing these exports. A daily/manual workflow opens a review PR against
`develop` when those canonical pages change; changes reach `main` through normal
promotion. `AGENTS.md`, `LLM_SPEC.md` and task templates remain local working rules.

Product/MCP installation, Python preparation, client configuration, native
packaging, signing and product release publication belong to private `spx-installer`.
Public model-only catalog publication belongs here and includes no installer code.
Get product packages through [SPX Downloads](https://staging.simplephysx.com/downloads).
`downloads.simplephysx.com` delivers authorized files. This public repository
has fresh history and contains no installer code, installer releases, product
Compose bundle or compatibility shims for older installers.
