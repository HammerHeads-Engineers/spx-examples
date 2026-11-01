# Maintain and publish the model library

The `Publish model catalog` workflow distributes public model data only.
Product installers, Python bootstrap, signing and product publication remain in
private `spx-installer`. No installer release is needed for a new model catalog.

## Branches and promotion

Contributions target `develop`. Its reviewed merges, after the required runtime
checks, produce immutable preview
releases named `catalog-preview.<run-id>`. Stable catalog versions are explicitly
chosen (for example `2026.11.01.1`) and published by manual dispatch from `main`
after the model changes have been reviewed and promoted there. The version is
independent of the server and Python package version. A `release/1.x` maintenance
branch becomes useful when the default line moves to a breaking server family;
it is not needed for every server patch version.

Repository maintainers should protect `develop` and `main`, require the public
contribution checks and review model/API changes. Configure the environments
`catalog-preview`, `catalog-qualification` and `catalog-stable`; use required
maintainer reviewers for stable publication and qualification as appropriate.
Fork PR jobs have read-only permissions and no runtime credentials. The release
workflow only publishes in the canonical repository from the designated branches.

## CI-managed qualification

Configure the secret `SPX_PRODUCT_KEY` in the GitHub environment
`catalog-qualification`, restricted to `main` and `develop`. The product key is
passed through the environment, never through workflow arguments or committed
files. Public fork/PR checks remain credential-free. There is no permanently
running qualification server or CI endpoint URL to maintain.
The publication workflow explicitly forwards the named secret to the reusable
workflow; its `workflow_call` declaration requires it. The environment-scoped
value takes precedence and remains restricted to the permitted branches.

`Model runtime compatibility` runs before preview/stable publication and by
manual dispatch without publication. It discovers the latest official
and RC server images from the public registry and retains all exact targets
declared by the candidate catalog. It freezes their version/digest matrix as a
workflow artifact. A newly published server does not silently change model
compatibility declarations.

Each matrix job creates its own disposable SPX Server, MQTT broker, software
KNX bus, LwM2M server and Matter controller service. Dependency images are pinned
in `tests/runtime/images.json`; test-only configs live alongside it. Only the
SPX API is published on an ephemeral loopback port. Resources come from the
candidate artifact. The harness collects key-redacted logs and removes its own
containers/network even after failures. These are CI fixtures, not product
installation or native-adapter provisioning recipes.

Declared compatibility targets are required checks. Latest official/RC versions
outside those declarations are advisory compatibility probes: their failures
are shown explicitly in the workflow summary and artifacts, and do not invent
support for an older or newer server. Initially the latest official release is
0.2.0 and the declared target is 1.0.0-rc.78; they are separate test rows. The
runtime checks verify the server's reported version rather than trusting a tag.

BLE examples are deferred to a later model release. Both remain in the source
library and preview catalogs with `distribution.channels: [preview]`. Stable
catalogs currently contain the other 95 models, with matching pack presets and
example-instance lists. Preview software checks record the two BLE exclusions
as a diagnostic subset. Stable checks must cover every model actually present
in the stable artifact; a partial report cannot qualify that artifact. Promoting
BLE requires adding its native/virtual Bluetooth test environment and updating
the channel policy together, rather than marking unavailable tests as passed.

The qualifier reads `/api/versions` itself and verifies the reported version
against the selected matrix target. For every compatible model it tests:
registration, instance creation with declared meta defaults, start to RUNNING,
three runtime cycles, finite JSON values, stop/start and cleanup. It records
individual failures without placing the key, base URL or raw server fault body
in the public report. It refuses a nonempty server and never skips a failed model
as a successful qualification. A diagnostic `--model` subset cannot qualify stable.

This baseline does not certify vendor fidelity or every wire mapping. Model
changes affecting transport behavior also need the corresponding protocol tests
and reviewer evidence. See `docs/RELEASE_MODEL_QA.md` and the model/pack integration
tests for deeper behavior, scenarios and protocol checks.

## Local rehearsal

After committing the exact candidate source:

```sh
poetry run python -m tools.check
poetry run python -m tools.catalog build --version preview.rehearsal --channel preview --output dist/rehearsal --require-clean
poetry run python -m tools.catalog release-manifest dist/rehearsal --channel preview
```

That verifies the preview artifact flow without publishing anything. To reproduce
the CI matrix locally, provide the key through your environment and run:

```sh
poetry run python -m tools.catalog build --version qa.local --channel stable --output dist/qa-local --require-clean
poetry run python -m tools.runtime_targets dist/qa-local --output dist/runtime-matrix.json
```

For each frozen matrix row, run `python -m tools.runtime_stack` with its exact
`--server-image`, `--expected-server` and `--output`. Advisory rows additionally
use `--probe-all`. The same harness and fixtures run on a local Docker engine.
Inspect `python -m tools.runtime_stack --help` for the complete interface.

The existing direct API qualifier also supports explicitly prepared, empty servers:

```sh
poetry run python -m tools.catalog qualify dist/qa-local --base-url http://localhost:18000 --allow-runtime-writes --output dist/qualification-1.0.0-rc.78.json
poetry run python -m tools.catalog release-manifest dist/qa-local --channel stable --qualification dist/qualification-1.0.0-rc.78.json
```

Stable metadata is refused unless full passing reports cover every declared
target and match the candidate catalog hash and source commit. Reports include
cleanup results. Static checks, an edited compatibility string or a diagnostic
subset do not satisfy this gate. Reports are trusted CI evidence; SHA-256 binds
them to artifacts, not to an independently authenticated issuer.

## Release assets and discovery

The workflow verifies the downloaded artifacts again, prepares `release.json`,
then creates a GitHub release as a draft with `catalog.json`, `model-files.zip`,
`release.json` and qualification reports when present. It exposes the release only
after uploads finish. Preview sets GitHub's pre-release flag. A previously used
release version is refused; maintainers must use a new version rather than
overwriting published artifacts. A failed unpublished draft should be inspected
and handled by a maintainer before retrying.

The GitHub Releases API is the channel index. Consumers filter `catalog-*` tags
and preview/stable status, then inspect the small release manifest and search
newest compatible candidates. There is no moving branch snapshot masquerading as
an immutable catalog. Retain previous releases for existing installations,
rollbacks and older server lines. The exact consumer contract is documented in
[CATALOG_CONTRACT.md](CATALOG_CONTRACT.md).
