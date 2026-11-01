# Contribute to the public model library

People and agents use the same flow and review criteria. The result is a durable,
reviewable repository change. For a local simulation without a library contribution,
use [the runtime workflow](docs/RUNTIME_WORKFLOW.md). Agents first resolve mode in
[AGENTS.md](AGENTS.md).

## 1. Prepare a checkout

Use Python 3.12 and Poetry 2.2.1, matching CI. Fork the repository on GitHub, replace
`YOUR_NAME` below with your account, then:

```sh
git clone https://github.com/YOUR_NAME/spx-examples.git
cd spx-examples
git remote add upstream https://github.com/HammerHeads-Engineers/spx-examples.git
git fetch upstream
git switch -c model/my-device upstream/develop
poetry install --with dev
```

For a maintainer checkout where `origin` is the canonical repository, branch from
`origin/develop` and use that reference in the checks below. Forks use
`upstream/develop`; fetch it again before preparing the final PR.

Read [model authoring rules](docs/LLM_SPEC.md) and the [model-language reference](docs/MODEL_LANGUAGE.md)
before substantive YAML work. Read a target pack's `SPEC.md` when applicable.
For documentation/tooling changes, use [the documentation map](docs/README.md) and
the touched component's tests; there is no requirement to add a model to such a PR.

## 2. Adapt the closest model

| Useful starting point | Catalog ID |
| --- | --- |
| MQTT telemetry | `Env.EnvSensor.Mqtt` |
| Modbus process control | `Process.ThermalController.Modbus` |
| SCPI instrument | `Lab.Multimeter.Scpi` |
| Protocol-free thermal behavior | `Process.ThermalController.Advanced` |

Create a minimal temperature draft:

```sh
poetry run python -m tools.catalog scaffold --id Community.Pt100 --name community_pt100 --description "Temperature demo" --pack embedded_lab_pack
```

Or preserve a twin's behavior while adapting its vendor/protocol mapping:

```sh
poetry run python -m tools.catalog scaffold --from Process.ThermalController.Modbus --id Community.Thermal --name community_thermal --description "Thermal controller demo" --pack industrial_iiot_pack
```

The scaffold creates a model/catalog draft and refreshes generated indexes and
README counts. It refuses existing IDs/paths and retains a twin's resource/license
metadata. Review behavior, units, endpoint parameters, bindings and evidence before
claiming the result works. Cite first-party vendor documentation for protocol maps.

## 3. Keep source and generated files distinct

| Edit this source | Responsibility |
| --- | --- |
| `library/domains/<group>/<class>/<vendor>/<name>.yaml` | Behavior, public state and communication parameters |
| `library/catalog/models.yaml` | Stable ID/path, taxonomy, protocols, service requirements and pack membership |
| `library/catalog/industries.yaml` | Pack descriptions, protocol presets and intentional example instances |
| `profiles/<pack>/` and the pack README | Runnable example configuration and instructions when affected |
| `library/catalog/distribution.yaml` | Maintainer-owned distribution defaults and exact qualification targets |
| `extensions/` or `library/assets/` | Helpers/resources explicitly declared in `distribution.resources` |
| `tests/` | Assertions proving behavior or a reported regression |

Preserve maintained model IDs, paths and public attributes. Use explicit
deprecation/replacement rather than silent removal. See [the catalog contract](docs/CATALOG_CONTRACT.md)
before changing compatibility, licensing, resource or channel metadata. New BLE
twins retain `distribution.channels: [preview]` until BLE qualification is available.

After manual membership edits, refresh generated pack indexes and README counts:

```sh
poetry run python -m tools.catalog refresh
```

Do not hand-edit `MODELS.yaml`, the README's generated overview or distribution
artifacts. Product references `docs/MODEL_LANGUAGE.md` and `docs/MCP.md` are also
generated; semantic changes belong upstream in `spx-docs`.

## 4. Validate what changed

Run the full shared, credential-free command. For the fork prepared above:

```sh
poetry run python -m tools.check --base-ref upstream/develop
```

It checks model/catalog consistency, documentation, generated indexes/counts,
distribution policy, archive integrity and unit tests. The base-reference check
also detects incompatible public model changes. Public PR CI uses the exact PR
base SHA. `--no-tests` is structural iteration only; it is not the final check.

Agents can save machine-readable evidence with:

```sh
poetry run python -m tools.check --json --report dist/contribution-checks.json
```

| Change | Additional evidence |
| --- | --- |
| Documentation | Check the reading route, local links, referenced commands and runnable example when changed |
| Tooling | Focused tests for observable behavior and relevant regressions |
| Model behavior | Assertions such as control → telemetry, unit conversion, alarm reset or scenario recovery |
| New model | A focused runtime smoke test: register, create/reset/start, verify useful behavior and clean up |
| Protocol binding | Actual relevant transport read/write results, with endpoint and server version |

The [runtime test template](templates/tests/test_temperature_behavior.py.example)
shows isolated names and cleanup. Put pack tests in `tests/packs/<pack>/integration/`
or shared protocol-free tests in `tests/core/runtime/`. Consult the installed
[Python client guide](examples/README.md#sdk-and-mcp-reference) for SDK use.

Run runtime tests only against an explicitly selected test server with credentials
supplied through the environment. Record unavailable tests as **unverified**, with
their reason; a skip is not proof of behavior. Public fork PR jobs need neither
a product key nor internal service access. Never include keys, private endpoints
or secret-bearing logs in YAML, examples, screenshots, reports or PR text.

## 5. Submit and understand publication

Push your branch and open a PR to `develop` with a Conventional Commit title,
for example `feat(models): add community thermal controller` or
`docs: clarify model contribution workflow`. Fill the PR template with purpose,
affected IDs, interface/compatibility decisions, sources and actual check results.
Maintainers review behavior, public interfaces, resources, licensing and tests.

```text
PR → credential-free checks + review → merge to develop
   → preview candidate + required runtime checks → preview publication
   → reviewed promotion to main
   → fresh stable candidate + full runtime qualification → stable publication
```

Trusted publication CI starts disposable servers and tests latest official/RC
images plus every declared target. Declared targets gate publication; advisory
probes expose limits without expanding compatibility. Deferred examples may stay
in preview. Every model actually in a stable artifact needs full qualification
bound to that exact catalog hash/source commit. See [release operations](docs/CATALOG_RELEASES.md).

Catalog publication does not change live instances. Current installer builds use
pinned public context; consuming published catalog releases is the integration
specified by [the installer consumer contract](docs/CATALOG_CONTRACT.md#installer-consumer-contract).

## Completion checklist

- The diff solves the stated task and preserves required public compatibility.
- Model contributions include catalog/resources, affected pack docs and useful tests.
- Generated files are current and the full shared checks pass.
- Runtime/protocol claims name the actual server and results; unavailable work is explicit.
- The PR targets `develop` and contains no credentials or product installation code.

Use [the task template](docs/LLM_TASK_TEMPLATE.md) for a model contribution and
[automation rules](docs/AUTOMATION.md) for model-generation automation. Local
validation alone does not mean the change is published or runtime-qualified.
