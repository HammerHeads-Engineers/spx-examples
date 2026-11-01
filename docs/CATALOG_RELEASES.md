# Maintain and publish the model library

The `Publish model catalog` workflow distributes public model data only.
Product installers, Python bootstrap, signing and product publication remain in
private `spx-installer`. No installer release is needed for a new model catalog.

## Branches and promotion

Contributions target `develop`. Its reviewed merges produce immutable preview
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

## Qualification environment setup

In the `catalog-qualification` GitHub environment configure:

- Secret `SPX_PRODUCT_KEY`, for the disposable qualification environment.
- Variable `SPX_CATALOG_QUALIFICATION_URLS`, JSON mapping each exact declared
  server target to its credential-free API base URL, for example
  `{"1.0.0-rc.78":"https://qualification.example.invalid"}`.

Provision dedicated servers and their protocol dependencies through the private
deployment/qualification infrastructure. The runner must be able to reach them.
Mount the catalog's reviewed `extensions/` resources where required by that
server. Endpoints must start with empty model and instance registries; never use
the user's working server. Different matrix targets need corresponding server
versions and isolated endpoints. The workflow serializes release runs.

Prepare the declared protocol services as well as the SPX API. Matter models
take their controller/fabric/node/endpoint through meta parameters; a node ID
such as `0x1234` is a provisioning example. BLE models require a running SPX BLE
Adapter on a supported macOS/Linux host with its Bluetooth backend available.
A Windows Docker server alone does not provide that adapter. Supply its URL
through `ble_adapter_base_url` in the prepared test environment; an unavailable
adapter is a failed qualification, not a reason to skip those catalog models.

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
poetry run python -m tools.catalog build --version preview.rehearsal --output dist/rehearsal --require-clean
poetry run python -m tools.catalog release-manifest dist/rehearsal --channel preview
```

That verifies the preview artifact flow without publishing anything. For real
runtime evidence, supply the key through your local environment and run:

```sh
poetry run python -m tools.catalog qualify dist/rehearsal --base-url http://localhost:18000 --allow-runtime-writes --output dist/qualification-1.0.0-rc.78.json
poetry run python -m tools.catalog release-manifest dist/rehearsal --channel stable --qualification dist/qualification-1.0.0-rc.78.json
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
