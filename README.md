# spx-examples

Public SPX models, industry packs, runnable examples, runtime MCP modules and
agent working instructions. The full product documentation lives at
[docs.simplephysx.com](https://docs.simplephysx.com).

## Choose your next step

| I want to… | Start here |
| --- | --- |
| Install SPX or configure an MCP client | [Installation Guide](https://docs.simplephysx.com/getting-started/installation-guide) |
| Understand model definitions in YAML or JSON | [Canonical model reference](https://docs.simplephysx.com/spx-development-guide/simulation-and-modeling/model-definition-reference), or [offline snapshot](docs/MODEL_LANGUAGE.md) |
| Find an existing model or industry pack | [Device Catalog](https://docs.simplephysx.com/usage-scenarios-and-examples/device-catalog), then `library/` below |
| Run my first simulation | [First simulation tutorial](https://docs.simplephysx.com/getting-started/build-your-first-simulation) |
| Work with a live server through an agent | [MCP reference](https://docs.simplephysx.com/getting-started/mcp-reference), or [offline snapshot](docs/MCP.md) |
| Contribute a model | [AGENTS.md](AGENTS.md), [modeling playbook](docs/LLM_SPEC.md), [task template](docs/LLM_TASK_TEMPLATE.md) |

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

The library can advance independently of packaged releases. An installed
bundle uses the public context revision pinned by its private installer build;
updating this checkout does not update installed services or their versions.

## Repository map

| Path | Contents |
| --- | --- |
| `library/domains/<domain_group>/<device_class>/<vendor>/` | Model YAML files |
| `library/catalog/` | Discovery, domain, pack and service metadata |
| `library/industries/` and `profiles/` | Pack instructions, indexes and presets |
| `examples/` and `extensions/` | Runnable scripts/notebooks and model helpers |
| `spx_mcp/` | Runtime MCP and catalog tools |
| `tests/` and `tools/` | Validation and contribution tooling |
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
The [canonical reference](https://docs.simplephysx.com/spx-development-guide/simulation-and-modeling/model-definition-reference)
provides equivalent JSON and explains units, actions, scenarios, timers and
parameterized communication. Library contributions use YAML and require a
catalog entry; JSON is supported at the API/import boundary.

## Development and validation

Use Python 3.12 (the CI baseline) and Poetry. MCP requires Python 3.10+.

```sh
poetry install --with dev
poetry run python tools/validate_models.py
poetry run python scripts/render_readme_catalog.py --check
poetry run pytest tests/core/unit tests/mcp/unit tests/packs/*/unit
```

The validator checks cataloged library models. To contribute the sample, place it
in the appropriate library directory and add its catalog entry as described in
`AGENTS.md`. Runtime validation additionally requires registering the model and
starting an instance on an already running SPX Server. Protocol proof is a
separate test when requested or needed to diagnose a failure.

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
packaging, signing and release publication belong to private `spx-installer`.
Get product packages through [SPX Downloads](https://staging.simplephysx.com/downloads).
`downloads.simplephysx.com` delivers authorized files. This public repository
has fresh history and contains no installer code, installer releases, product
Compose bundle or compatibility shims for older installers.
