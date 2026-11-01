# Contribute models with a person or an agent

This is the public source of SPX models and pack membership. A contribution is a
reviewable change to this repository. Product installation and client setup live
in private `spx-installer`. The public catalog can be released independently of
that installer. Local runtime experiments follow the separate `runtime_mcp` path
in [AGENTS.md](AGENTS.md); they are not automatically library contributions.

## 1. Prepare a checkout

Use Python 3.12 and Poetry 2.2.1, the CI baseline. Fork the repository, branch
from `develop`, then install the development dependencies:

```sh
git switch develop
git switch -c model/my-device
poetry install --with dev
```

Read [the modeling playbook](docs/LLM_SPEC.md) and the pinned
[model-language reference](docs/MODEL_LANGUAGE.md). Product semantics are owned
by `spx-docs`; do not hand-edit generated offline references.

## 2. Create a draft

Start with the nearest existing behavioral twin. These are useful entry points:

| Intent | Existing model ID to inspect or copy |
| --- | --- |
| MQTT telemetry | `Env.EnvSensor.Mqtt` |
| Modbus process control | `Process.ThermalController.Modbus` |
| SCPI instrument | `Lab.Multimeter.Scpi` |
| Protocol-free thermal behavior | `Process.ThermalController.Advanced` |

To create a minimal temperature draft:

```sh
poetry run python -m tools.catalog scaffold --id Community.Pt100 --name community_pt100 --description "Temperature demo" --pack embedded_lab_pack
```

To preserve a twin's behavior and adapt its vendor/protocol mapping:

```sh
poetry run python -m tools.catalog scaffold --from Process.ThermalController.Modbus --id Community.Thermal --name community_thermal --description "Thermal controller demo" --pack industrial_iiot_pack
```

The command creates the model and catalog entry and refreshes generated pack
indexes and README counts. It refuses to overwrite an existing ID or path.
It produces a **draft**: review physics, names, units, endpoint parameters and
protocol bindings before treating it as a working device. Cloning a model keeps
its declared resources and license metadata.

## 3. Understand the files you own

| Source | What to edit |
| --- | --- |
| `library/domains/<group>/<class>/<vendor>/<name>.yaml` | Device behavior, public attributes, communication parameters |
| `library/catalog/models.yaml` | Stable ID, display name, taxonomy, protocols, required service IDs, packs, optional distribution overrides |
| `library/catalog/industries.yaml` | A pack's description, default protocols and example-instance declarations |
| `library/catalog/distribution.yaml` | Maintainer-owned defaults and exact server qualification targets |
| `extensions/` or `library/assets/` | Explicit model resources, declared in `distribution.resources` |
| `tests/` | Assertions demonstrating the requested behavior and regressions |

Keep IDs, existing public attributes and paths stable. Deprecate an existing
model with a replacement reference instead of removing it from a maintained
line. See [the distribution contract](docs/CATALOG_CONTRACT.md) for compatibility
overrides and [release operations](docs/CATALOG_RELEASES.md) for promotion rules.
Models deferred from a stable release stay in the library with
`distribution.channels: [preview]`. BLE examples currently follow this policy
until native/virtual BLE runtime QA is added; retain that policy for new BLE twins.

Generated `library/industries/*/MODELS.yaml`, README counts and distribution
artifacts are derived from source catalogs. After manual membership edits run:

```sh
poetry run python -m tools.catalog refresh
```

## 4. Test and review

Run the same credential-free entry point as public CI:

```sh
poetry run python -m tools.check
```

It checks model/catalog consistency, generated indexes, README counts, distribution
metadata, export integrity and unit tests. A nonzero exit code means the PR is
not ready. For rapid structural iteration only, use `--no-tests`.
Public PR CI also compares IDs, paths, public attributes/meta parameters/scenarios
and previous server targets with the exact PR base. Before opening a PR, run
`poetry run python -m tools.check --no-tests --base-ref origin/develop` to inspect
that compatibility check locally.

Agents can consume one JSON document and preserve it as evidence:

```sh
poetry run python -m tools.check --json --report dist/contribution-checks.json
```

Add assertions that exercise useful behavior: a control changes telemetry,
unit conversion is correct, an alarm resets, or a protocol point reads/writes
the intended state. [The temperature test template](templates/tests/test_temperature_behavior.py.example)
shows a control-to-telemetry test with isolated names and cleanup. Adapt it to
your model; validate claimed protocol behavior on the corresponding transport.
The shared runtime catalog tests also cover every registered catalog entry.

Static validation does not establish runtime compatibility. Runtime tests need
an explicitly prepared test server and a locally supplied `SPX_PRODUCT_KEY`;
public fork PR checks need neither a license key nor access to internal services.
Never put credentials in YAML, examples, PR text, screenshots or test reports.
Trusted release CI starts disposable servers itself and tests the latest official
and RC server images alongside every declared compatibility target. Required
targets gate publication; advisory probes expose compatibility limits without
automatically widening declarations. Fork PRs do not receive the product secret.

## 5. Open the PR

Target `develop` and use a Conventional Commit title, for example
`feat(models): add community thermal controller`. Use the PR template to record
the model IDs, purpose, compatibility declaration and actual test results. Keep
unverified claims explicit. Maintainers review behavior, public interfaces,
resources, licensing and tests before merging.

```text
Draft -> local checks -> PR + public CI -> maintainer review
      -> develop / preview -> runtime qualification -> main / stable catalog
```

A preview is discoverable as experimental catalog content, not a certificate of
device fidelity. Stable catalog publication requires runtime evidence bound to
the exact catalog hash and source commit. Library releases do not update a user's
running instances. The installer chooses a compatible published catalog and
records the exact revision when the user confirms installation.

## Agent completion checklist

- Work in `repo_dev` for a persistent community contribution.
- Inspect the nearest model and required references before editing.
- Preserve behavior when adapting a vendor twin; describe intentional changes.
- Include the catalog entry, declared resources and meaningful tests.
- Refresh generated indexes and run the full shared check command.
- Report model IDs, edited files, command results and any unverified runtime work.
- Finish with a reviewable diff/PR; do not claim publication or compatibility from
  static checks alone.
