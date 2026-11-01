"""Public model distribution contract, independent of product installation.

Only model definitions and explicitly declared resources are exported. Deployment
commands, credentials, MCP modules and client configuration are not catalog data.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import yaml
from jsonschema import Draft202012Validator
from semantic_version import SimpleSpec, Version

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
MODEL_METADATA = {
    "server_compatibility",
    "license",
    "resources",
    "status",
    "replaced_by",
}


class CatalogError(ValueError):
    """An actionable catalog or artifact validation failure."""


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"{path}: cannot read YAML: {exc}") from exc


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise CatalogError(
            "A Git checkout is required to record catalog provenance"
        ) from exc


def safe_file(root: Path, value: str, *, resource=False) -> Path:
    if (
        not isinstance(value, str)
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
    ):
        raise CatalogError(f"Invalid POSIX resource path: {value!r}")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.as_posix() != value
        or any(p in {".", ".."} or p.startswith(".") for p in value.split("/"))
    ):
        raise CatalogError(f"Unsafe catalog path: {value!r}")
    prefixes = (
        ("library/assets/", "extensions/")
        if resource
        else ("library/domains/", "library/assets/", "extensions/")
    )
    if not value.startswith(prefixes) and not (not resource and value == "LICENSE"):
        raise CatalogError(
            f"{value}: only model files and declared library/assets or extensions resources may be exported"
        )
    path = root / value
    if not path.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in [path, *path.parents] if p != root.parent
    ):
        raise CatalogError(
            f"{value}: symlinks and paths outside the checkout are not allowed"
        )
    if not path.is_file():
        raise CatalogError(
            f"{value}: missing file; add it to the repository and declare it in distribution.resources"
        )
    return path


def source_files(root: Path, names, *, committed: bool) -> dict[str, bytes]:
    """Published bytes come from Git blobs, independent of checkout CRLF rules."""
    for name in names:
        safe_file(root, name)
    if not committed:
        return {name: (root / name).read_bytes() for name in names}
    tree = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD"]
    )
    entries = {}
    for row in tree.split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            entries[path.decode("utf-8")] = metadata.split()
    for name in names:
        if name not in entries or entries[name][0] not in {b"100644", b"100755"}:
            raise CatalogError(f"{name}: commit a regular file before publishing")
    request = b"".join(entries[name][2] + b"\n" for name in names)
    stream = io.BytesIO(
        subprocess.check_output(
            ["git", "-C", str(root), "cat-file", "--batch"], input=request
        )
    )
    result = {}
    for name in names:
        _, kind, size = stream.readline().split()
        if kind != b"blob":
            raise CatalogError(f"{name}: expected a committed blob")
        result[name] = stream.read(int(size))
        if stream.read(1) != b"\n":
            raise CatalogError("Invalid Git blob stream")
    return result


def server_matches(spec: str, server: str) -> bool:
    try:
        # Ranges use documented SimpleSpec syntax, including explicit RC versions.
        return SimpleSpec(spec).match(Version(server.removeprefix("v")))
    except (TypeError, ValueError) as exc:
        raise CatalogError(
            f"Invalid server version/range: {server!r} / {spec!r}"
        ) from exc


def validate_schema(document: dict, root: Path = ROOT) -> None:
    schema = json.loads(
        (root / "schemas/model-catalog.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda e: str(list(e.path)),
    )
    if errors:
        error = errors[0]
        raise CatalogError(
            f"catalog.json/{'/'.join(map(str, error.path))}: {error.message}"
        )
    for key, identity in (
        ("models", "id"),
        ("packs", "id"),
        ("services", "id"),
        ("files", "path"),
    ):
        values = [entry[identity] for entry in document[key]]
        if len(set(values)) != len(values):
            raise CatalogError(f"catalog.json: duplicate {key}/{identity}")
    ids = {m["id"] for m in document["models"]}
    packs = {p["id"] for p in document["packs"]}
    services = {s["id"] for s in document["services"]}
    for model in document["models"]:
        if set(model["packages"]) - packs or set(model["required_services"]) - services:
            raise CatalogError(f"{model['id']}: unknown pack or service reference")
        if model["replaced_by"] is not None and model["replaced_by"] not in ids - {
            model["id"]
        }:
            raise CatalogError(f"{model['id']}: invalid replacement reference")
        for target in document["qualification_targets"]:
            server_matches(model["server_compatibility"], target)
    for pack in document["packs"]:
        expected = {m["id"] for m in document["models"] if pack["id"] in m["packages"]}
        if set(pack["recommended_model_ids"]) != expected:
            raise CatalogError(f"{pack['id']}: inconsistent recommended model IDs")
        if any(entry["model"] not in expected for entry in pack["default_instances"]):
            raise CatalogError(
                f"{pack['id']}: default instance references a model outside the pack"
            )
        if set(pack["start_instances"]) - {
            entry["instance"] for entry in pack["default_instances"]
        }:
            raise CatalogError(
                f"{pack['id']}: auto-start references an unknown default instance"
            )


def distribution_config(root: Path) -> dict:
    path = root / "library/catalog/distribution.yaml"
    config = read_yaml(path)
    fields = {
        "schema_version",
        "library_id",
        "repository",
        "license",
        "server_compatibility",
        "qualification_targets",
    }
    if (
        not isinstance(config, dict)
        or set(config) != fields
        or config["schema_version"] != 1
    ):
        raise CatalogError(
            f"{path}: expected schema_version 1 and fields {sorted(fields)}"
        )
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", config["repository"])
        or not config["license"]
    ):
        raise CatalogError(
            f"{path}: repository and SPDX license identifier are required"
        )
    targets = config["qualification_targets"]
    if (
        not isinstance(targets, list)
        or not targets
        or len(set(targets)) != len(targets)
    ):
        raise CatalogError(
            f"{path}: qualification_targets must contain unique exact server versions"
        )
    for target in targets:
        if not server_matches(config["server_compatibility"], target):
            raise CatalogError(
                f"{path}: qualification target {target} does not match server_compatibility"
            )
    return config


def _local_imports(value):
    """Find repo-local Python bindings without importing or executing model code."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"python_file", "import"} and isinstance(item, dict):
                for filename in item:
                    if isinstance(filename, str) and filename.endswith(".py"):
                        yield filename
            if key == "imports" and isinstance(item, dict):
                for module in item.values():
                    if isinstance(module, str) and module.startswith("extensions."):
                        yield module
            yield from _local_imports(item)
    elif isinstance(value, list):
        for item in value:
            yield from _local_imports(item)


def model_files(root: Path, entry: dict, definition: dict, metadata: dict) -> list[str]:
    resources = metadata.get("resources", [])
    if not isinstance(resources, list) or len(set(resources)) != len(resources):
        raise CatalogError(
            f"{entry['id']}: distribution.resources must be a unique list of file paths"
        )
    for resource in resources:
        safe_file(root, resource, resource=True)
    for imported in _local_imports(definition):
        if imported.endswith(".py"):
            needed = imported
        else:
            parts = imported.split(".")
            while parts and not (root / ("/".join(parts) + ".py")).is_file():
                parts.pop()
            needed = "/".join(parts) + ".py"
        if needed not in resources:
            raise CatalogError(
                f"{entry['path']}: declare local import {imported!r} as {needed!r} in distribution.resources"
            )
    return sorted({entry["path"], *resources})


def build_document(root: Path, version: str, *, require_clean=False) -> dict:
    root = root.resolve()
    if not VERSION_RE.fullmatch(version):
        raise CatalogError(
            "Catalog version must contain only letters, digits, dots, underscores and hyphens"
        )
    from tools.validate_models import validate_models

    validation = validate_models(root)
    if not validation.ok():
        raise CatalogError("\n".join(validation.errors))
    config = distribution_config(root)
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=normal"))
    if dirty and require_clean:
        raise CatalogError(
            "Commit the source changes first: published catalogs require a clean Git checkout"
        )
    entries = read_yaml(root / "library/catalog/models.yaml")["models"]
    ids = {entry["id"] for entry in entries}
    services = read_yaml(root / "library/catalog/services.yaml")["services"]
    service_ids = {service["id"] for service in services}
    models = []
    files = {"LICENSE"}
    for entry in sorted(entries, key=lambda item: item["id"]):
        path = safe_file(root, entry["path"])
        definition = read_yaml(path)
        metadata = entry.get("distribution", {})
        if not isinstance(metadata, dict) or set(metadata) - MODEL_METADATA:
            raise CatalogError(
                f"{entry['id']}: unknown distribution metadata; supported: {sorted(MODEL_METADATA)}"
            )
        spec = metadata.get("server_compatibility", config["server_compatibility"])
        if not any(
            server_matches(spec, target) for target in config["qualification_targets"]
        ):
            raise CatalogError(
                f"{entry['id']}: add a matching qualification target before declaring {spec}"
            )
        required = sorted(
            {
                service if isinstance(service, str) else service["id"]
                for service in entry["services"]
            }
        )
        if set(required) - service_ids:
            raise CatalogError(
                f"{entry['id']}: unknown required service IDs: {sorted(set(required) - service_ids)}"
            )
        resources = model_files(root, entry, definition, metadata)
        files.update(resources)
        status = metadata.get("status", "active")
        replacement = metadata.get("replaced_by")
        if replacement is not None and (
            replacement not in ids or replacement == entry["id"]
        ):
            raise CatalogError(
                f"{entry['id']}: replaced_by must reference another catalog model"
            )
        models.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "description": definition.get("description", "").strip(),
                "path": entry["path"],
                "domain_group": entry["domain_group"],
                "device_class": entry["device_class"],
                "vendor": entry["vendor"],
                "protocols": sorted(set(entry["protocols"])),
                "packages": sorted(set(entry["packages"])),
                "required_services": required,
                "server_compatibility": spec,
                "license": metadata.get("license", config["license"]),
                "status": status,
                "replaced_by": replacement,
                "files": resources,
            }
        )
    packs = []
    for pack in sorted(
        read_yaml(root / "library/catalog/industries.yaml")["industries"],
        key=lambda item: item["id"],
    ):
        packs.append(
            {
                "id": pack["id"],
                "name": pack["name"],
                "description": pack["description"].strip(),
                "default_protocols": sorted(set(pack["protocols"])),
                "recommended_model_ids": [
                    m["id"] for m in models if pack["id"] in m["packages"]
                ],
                "default_instances": pack.get("default_instances", []),
                "start_instances": pack.get("start_instances", []),
            }
        )
    content = source_files(root, sorted(files), committed=not dirty)
    document = {
        "schema_version": 1,
        "catalog_version": version,
        "library_id": config["library_id"],
        "source": {
            "repository": config["repository"],
            "commit": git(root, "rev-parse", "HEAD"),
            "dirty": dirty,
        },
        "qualification_targets": config["qualification_targets"],
        "license": config["license"],
        "models": models,
        "packs": packs,
        "services": [
            {key: service[key] for key in ("id", "name", "protocol", "description")}
            for service in sorted(services, key=lambda s: s["id"])
        ],
        "files": [
            {"path": name, "sha256": digest(data), "size": len(data)}
            for name, data in content.items()
        ],
    }
    validate_schema(document, root)
    return document


def export_catalog(
    root: Path, output: Path, version: str, *, require_clean=False
) -> dict:
    document = build_document(root, version, require_clean=require_clean)
    encoded = json_bytes(document)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "catalog.json"
    if target.exists() and target.read_bytes() != encoded:
        raise CatalogError(
            f"{output}: contains a different catalog; choose a new output directory"
        )
    content = source_files(
        root,
        [file["path"] for file in document["files"]],
        committed=not document["source"]["dirty"],
    )
    for file in document["files"]:
        destination = output / "files" / file["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content[file["path"]])
    target.write_bytes(encoded)
    with zipfile.ZipFile(
        output / "model-files.zip", "w", compression=zipfile.ZIP_STORED
    ) as archive:
        for file in document["files"]:
            info = zipfile.ZipInfo(file["path"], date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (output / "files" / file["path"]).read_bytes())
    verify_catalog(output)
    return document


def verify_catalog(directory: Path) -> dict:
    document = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    validate_schema(document)
    expected = {file["path"]: file for file in document["files"]}
    actual = {
        p.relative_to(directory / "files").as_posix()
        for p in (directory / "files").rglob("*")
        if p.is_file()
    }
    if actual != set(expected):
        raise CatalogError("Exported file set does not match catalog.json")
    for name, record in expected.items():
        data = safe_file(directory / "files", name).read_bytes()
        if len(data) != record["size"] or digest(data) != record["sha256"]:
            raise CatalogError(f"{name}: size/SHA-256 mismatch")
    with zipfile.ZipFile(directory / "model-files.zip") as archive:
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(
            expected
        ):
            raise CatalogError("Archive file set does not match catalog.json")
        for name, record in expected.items():
            if digest(archive.read(name)) != record["sha256"]:
                raise CatalogError(f"{name}: archive SHA-256 mismatch")
    for model in document["models"]:
        if model["path"] not in model["files"] or set(model["files"]) - set(expected):
            raise CatalogError(f"{model['id']}: incomplete file closure")
    return document


def select_models(
    document: dict, server: str, *, protocols=(), pack=None, include_deprecated=False
) -> list[dict]:
    """Reference selection semantics shared by agents and installer consumers."""
    if pack is not None and pack not in {p["id"] for p in document["packs"]}:
        raise CatalogError(f"Unknown pack: {pack}")
    known_protocols = {
        p for model in document["models"] for p in model["protocols"]
    } | {s["protocol"] for s in document["services"]}
    if set(protocols) - known_protocols:
        raise CatalogError(
            f"Unknown protocols: {sorted(set(protocols) - known_protocols)}"
        )
    return [
        model
        for model in document["models"]
        if server_matches(model["server_compatibility"], server)
        and (include_deprecated or model["status"] == "active")
        and (pack is None or pack in model["packages"])
        and (
            not protocols
            or set(protocols).intersection(model["protocols"])
            or (pack is not None and not model["protocols"])
        )
    ]


def release_manifest(directory: Path, channel: str, reports: list[Path]) -> dict:
    document = verify_catalog(directory)
    if channel not in {"preview", "stable"} or document["source"]["dirty"]:
        raise CatalogError(
            "Publishing requires a clean catalog and channel preview or stable"
        )
    catalog_hash = digest((directory / "catalog.json").read_bytes())
    qualification = []
    for report_path in reports:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or report.get("schema_version") != 1
            or not isinstance(report.get("server_version"), str)
            or not isinstance(report.get("results"), list)
            or not all(isinstance(row, dict) for row in report["results"])
        ):
            raise CatalogError(
                f"{report_path}: expected a schema_version 1 qualification report"
            )
        server = report.get("server_version")
        expected = {
            m["id"] for m in select_models(document, server, include_deprecated=True)
        }
        results = report.get("results", [])
        if (
            report.get("catalog_sha256") != catalog_hash
            or report.get("source_commit") != document["source"]["commit"]
            or report.get("status") != "PASSED"
            or report.get("scope") != "full-catalog"
            or not expected
            or len(results) != len(expected)
            or {r.get("model_id") for r in results} != expected
            or any(
                any(
                    r.get(field) != "PASSED"
                    for field in (
                        "registration",
                        "startup",
                        "behavior",
                        "lifecycle",
                        "cleanup",
                    )
                )
                for r in results
            )
        ):
            raise CatalogError(
                f"{report_path}: qualification must cover every compatible model and lifecycle check for this exact catalog"
            )
        if server in {item["server_version"] for item in qualification}:
            raise CatalogError(f"Duplicate qualification report for server {server}")
        qualification.append(
            {
                "server_version": server,
                "sha256": digest(report_path.read_bytes()),
                "file": f"qualification-{server}.json",
            }
        )
    if channel == "stable" and {q["server_version"] for q in qualification} != set(
        document["qualification_targets"]
    ):
        raise CatalogError(
            "Stable requires passing runtime qualification for every declared server target"
        )
    return {
        "schema_version": 1,
        "channel": channel,
        "catalog_version": document["catalog_version"],
        "source": document["source"],
        "qualification_targets": document["qualification_targets"],
        "catalog": {"file": "catalog.json", "sha256": catalog_hash},
        "model_archive": {
            "file": "model-files.zip",
            "sha256": digest((directory / "model-files.zip").read_bytes()),
        },
        "qualification": qualification,
    }
