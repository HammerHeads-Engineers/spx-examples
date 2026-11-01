# SPX public model library

Find a simulation model, run it on SPX, or contribute a reusable model for other
people and agents. This repository contains model YAML, industry packs, examples,
runtime MCP tools and the checks used to review community contributions.

## Start with your task

| Your goal | Start here | Expected result |
| --- | --- | --- |
| Find and use a model | [Library overview](#library-overview), [published catalogs](https://github.com/HammerHeads-Engineers/spx-examples/releases) and [first example](examples/README.md) | A suitable model and a verified running example |
| Work on a live server with an agent | [Runtime workflow](docs/RUNTIME_WORKFLOW.md) | A working instance, scenario or connection on that server |
| Add or improve a shared model | [Contributing](CONTRIBUTING.md) | A tested, reviewable PR to `develop` |
| Maintain or consume catalog releases | [Catalog contract](docs/CATALOG_CONTRACT.md) and [release operations](docs/CATALOG_RELEASES.md) | A pinned catalog with explicit compatibility and evidence |

Need to install SPX first? Follow the product
[installation guide](https://docs.simplephysx.com/readme/installation-guide).
Use [the documentation map](docs/README.md) to find syntax, agent rules and QA notes.

## Library overview

<!-- catalog-overview:start -->

Source library: **97 models** across 5 domain groups.

Channel eligibility in this checkout: **97 preview / 95 stable**.
These counts describe source policy; released contents and qualification are recorded in release assets.

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

Source membership and release qualification answer different questions. For a
published catalog's exact model set and tested server versions, inspect its
`catalog.json`, `release.json` and qualification reports. A protocol tag identifies
an interface; lifecycle qualification does not certify every wire mapping.
BLE models remain preview-only pending separate BLE qualification.

## Run your first example

Use a running SPX test server and the Python client to change a temperature input,
read the resulting telemetry, and clean up the example's own model and instance.
The [example quickstart](examples/README.md#first-success-temperature-telemetry)
provides Windows and Linux/macOS setup, the command, expected output and recovery
steps. It needs no external protocol service or physical device.

## Minimal model: temperature input and telemetry

This complete definition demonstrates the same input/output relationship:

<!-- spx-model-example -->
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

`k__temperature_c` is a persistent control input; `temperature_c` is telemetry.
This simulates temperature telemetry rather than PT100 electrical resistance.
The [model reference](docs/MODEL_LANGUAGE.md) defines the language and equivalent
JSON form. Library contributions use YAML; the API/import boundary also accepts JSON.

## Contribute and validate

For a development checkout, use Python 3.12 and Poetry 2.2.1, matching CI:

```sh
poetry install --with dev
poetry run python -m tools.check
```

The shared credential-free check covers models, catalogs, documentation,
generated indexes, archive integrity and unit tests on Windows and Linux.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete fork-to-PR flow and scaffold
command. Agents start with [AGENTS.md](AGENTS.md) and read task-specific guidance.
Local live work follows the smaller [runtime workflow](docs/RUNTIME_WORKFLOW.md).

## Repository map

| Path | Responsibility |
| --- | --- |
| `library/domains/<group>/<class>/<vendor>/` | Model YAML: behavior, state and protocol bindings |
| `library/catalog/` | IDs, discovery, pack membership, services and distribution policy |
| `library/industries/` and `profiles/` | Pack documentation, generated indexes and presets |
| `examples/` | Runnable tutorials, scripts and notebooks |
| `extensions/` | Helpers explicitly required by models |
| `spx_mcp/` | Repository-aware catalog tools and live-server MCP operations |
| `tests/`, `tools/`, `scripts/` | Behavior tests, validation and maintenance commands |
| `schemas/` and `templates/` | Catalog schema and contribution starters |
| `docs/` | Task guides, catalog contracts and pinned offline product references |

## Ownership and versions

[spx-docs](https://docs.simplephysx.com) owns product behavior, model-language
semantics and public API reference. This repository owns practical examples,
library conventions, contribution workflows and model-catalog releases.
`docs/MODEL_LANGUAGE.md` and `docs/MCP.md` are generated snapshots pinned by
[docs-source.json](docs-source.json); propose semantic corrections upstream.

Catalog versions, catalog schema versions, SPX Server versions, Python package
versions and installer versions are independent. Compatibility belongs in
[catalog metadata](docs/CATALOG_CONTRACT.md#compatibility-and-versions) and is
verified against actual servers before stable publication.

Product installation, client configuration, packaging and signing belong to the
private `spx-installer` repository. Its current builds use pinned public context;
the [published-catalog consumer contract](docs/CATALOG_CONTRACT.md#installer-consumer-contract)
describes the integration to implement there. Updating this checkout or publishing
a catalog does not migrate installed services or live instances.
