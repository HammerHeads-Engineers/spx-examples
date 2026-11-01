# Public model catalog contract (schema version 1)

This repository owns model distribution metadata. Product language semantics
remain in `spx-docs`; this contract does not introduce new runtime YAML fields.

## Authoritative inputs

`library/catalog/models.yaml` owns model IDs and pack membership.
`industries.yaml` owns pack descriptions and protocol presets. Model YAML owns
behavior and descriptions. `distribution.yaml` declares a catalog schema,
repository identity, default SPDX license, default server compatibility and exact
runtime qualification targets. Generated indexes and JSON are never edited by hand.

Every YAML under `library/domains/` must have a model entry or an explicit
`unpublished_models` entry in `models.yaml` with a canonical `path` and a nonempty
`reason`. The latter retains diagnostics or drafts without making them available
to installers. Unpublished files cannot be pack/profile members and are never
exported. To publish one, replace that declaration with a complete model entry
and the required behavior tests.

Models inherit defaults. An entry may override distribution metadata:

```yaml
distribution:
  server_compatibility: '==1.0.0-rc.78'
  license: MIT
  resources:
    - extensions/thermal_model.py
  status: active
  channels: [preview, stable]
```

`resources` lists individual repository files under `extensions/` or
`library/assets/`. Include every helper and its own required local resources.
Local Python bindings are inspected without executing their code; undeclared
direct imports fail validation. Directories, symlinks, traversal, hidden files,
MCP modules and installation scripts are outside the export boundary. Dynamic
resource dependencies still require explicit declarations and runtime tests.

To deprecate a model, set `status: deprecated` and optionally `replaced_by` to an
existing different model ID. Keep the old entry available for existing users.

`channels` defaults to `[preview, stable]`. A model under evaluation can use
`[preview]` while retaining its source ID and path. `build --channel stable`
omits those definitions/resources and filters pack protocol presets, default
instances and auto-start lists to the models in that artifact. The default build
channel is preview. The release manifest records the channel; the catalog v1
JSON shape remains the same, as a self-contained snapshot of its published
models. The two BLE examples are currently preview-only pending separate BLE QA.

## Compatibility and versions

The catalog version, its JSON schema version and the server version are separate.
`pyproject.toml` versions the Python package, not the public model catalog.
`server_compatibility` uses `semantic_version.SimpleSpec` syntax, with full
SemVer versions and comma-separated clauses, for example `>=1.1.0,<2.0.0`.
Pre-release handling follows SimpleSpec: explicit RC bounds/equality should be
used for RC qualification, rather than assuming a stable range includes RCs.

The initial default is the exact declared target `1.0.0-rc.78`. It is a
declaration, not proof that every model works there. Do not broaden it to 1.1.x
or all 1.x based only on structural validation. An override needs at least one
matching `qualification_targets` entry, and stable publication requires passing
reports for every declared target. A maintained line must retain existing IDs,
public attributes and compatibility; breaking variants need an explicit migration
and a retained usable previous release.

## Build and inspect

```sh
poetry run python -m tools.catalog build --version preview.local --channel preview --output dist/catalog-local
poetry run python -m tools.catalog verify dist/catalog-local
poetry run python -m tools.catalog list dist/catalog-local --server 1.0.0-rc.78 --protocol modbus
poetry run python -m tools.catalog list dist/catalog-local --server 1.0.0-rc.78 --pack industrial_iiot_pack --protocol mqtt
```

The output contains:

- `catalog.json`: schema-validated discovery metadata, source commit, model and
  pack definitions, required service IDs, explicit file closure, sizes and SHA-256.
- `files/`: model definitions, declared resources and `LICENSE` at original paths.
- `model-files.zip`: deterministic offline archive of exactly those files.

Clean published builds read committed Git blobs, so Git checkout newline settings
on Windows cannot change file hashes relative to the public commit. Dirty local
drafts are marked `source.dirty: true` and cannot produce publication metadata.
Use `--require-clean` for release builds. A directory containing a different
catalog is not overwritten; choose a fresh version/output directory.

The generated JSON Schema is defined in `schemas/model-catalog.schema.json`.
Its version is explicit; clients must reject unsupported schema versions.
Service entries contain identity, protocol and descriptions, not executable
deployment recipes. The installer owns local adapter support, Docker images,
Python preparation and host-specific policy (including Windows BLE availability).

## Selection semantics

Filter on the actual target server before calculating counts. A pack recommends
its members compatible with at least one chosen protocol, plus its protocol-free
simulation models. Custom protocol selection chooses matching models across the
catalog. Deprecated entries are excluded from new suggestions by default, while
`--include-deprecated` supports inspection and migration. A model's files are its
YAML and declared resources; `required_services` are requirements for installer
resolution and do not add arbitrary commands to the catalog.

## Installer consumer contract

1. Discover published `catalog-*` GitHub releases in this public repository;
   preview releases are marked pre-release and stable releases are not.
2. Fetch the small `release.json` asset. Verify the channel, supported schema,
   source repository and candidate qualification target before fetching metadata.
3. Fetch `catalog.json` and verify its SHA-256 against `release.json`. Filter
   per-model compatibility to obtain pack/protocol suggestions.
4. Keep that catalog pinned for the whole wizard session, including Back.
5. After confirmation, fetch only selected model/resource paths from the exact
   source commit and verify each size/hash. Alternatively use the verified offline
   archive, extracting only listed paths with the same path-boundary checks.
6. Record catalog version, source commit, selected IDs and file hashes in the
   installation lock. Refreshing discovery metadata does not migrate live instances.

Discovery must paginate GitHub release results when searching older compatible
catalogs. An unknown version, unavailable file or hash mismatch must not silently
fall back to a moving branch. Offline use requires a previously verified compatible
catalog/cache. Runtime MCP code and product installation keep independent releases.
