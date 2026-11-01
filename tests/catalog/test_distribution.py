"""Contract tests: provenance, reproducibility, selection and publication gates."""

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from tools.model_catalog import (
    ROOT,
    CatalogError,
    build_document,
    digest,
    export_catalog,
    json_bytes,
    release_manifest,
    safe_file,
    select_models,
    server_matches,
    verify_catalog,
)
from tools.scaffold_model import scaffold


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    root = tmp_path_factory.mktemp("catalog-source")
    for name in ("extensions", "schemas"):
        shutil.copytree(ROOT / name, root / name)
    catalog = root / "library/catalog"
    catalog.mkdir(parents=True)
    (root / "profiles").mkdir()
    for name in ("domains.yaml", "services.yaml", "distribution.yaml"):
        shutil.copyfile(ROOT / "library/catalog" / name, catalog / name)
    for domain in ("building", "environment", "industrial", "energy", "lab"):
        (root / "library/domains" / domain).mkdir(parents=True)
    chosen = {
        "Process.ThermalController.Advanced",
        "Energy.CSMS.Ocpp",
        "Env.EnvSensor.Mqtt",
    }
    entries = yaml.safe_load(
        (ROOT / "library/catalog/models.yaml").read_text(encoding="utf-8")
    )["models"]
    entries = [entry for entry in entries if entry["id"] in chosen]
    for entry in entries:
        entry["profiles"] = []
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry["path"], target)
    (catalog / "models.yaml").write_text(
        yaml.safe_dump({"models": entries}, sort_keys=False), encoding="utf-8"
    )
    industries = yaml.safe_load(
        (ROOT / "library/catalog/industries.yaml").read_text(encoding="utf-8")
    )["industries"]
    for pack in industries:
        pack.update({"profiles": [], "default_instances": [], "start_instances": []})
        directory = root / pack["path"]
        directory.mkdir(parents=True)
        (directory / "README.md").write_text("Test pack", encoding="utf-8")
    (catalog / "industries.yaml").write_text(
        yaml.safe_dump({"industries": industries}, sort_keys=False), encoding="utf-8"
    )
    for name in ("README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, root / name)
    from tools.scaffold_model import refresh

    refresh(root)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "catalog-test@example.invalid"),
        ("config", "user.name", "Catalog test"),
        ("config", "core.autocrlf", "input"),
        ("add", "."),
        ("commit", "-qm", "fixture"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def test_real_public_library_exports_without_deployment_code(tmp_path):
    document = export_catalog(ROOT, tmp_path / "real-library", "local-real-library")
    assert len(document["models"]) >= 90
    assert all("deployment" not in service for service in document["services"])


@pytest.fixture
def source(baseline, tmp_path):
    root = tmp_path / "source"
    shutil.copytree(baseline, root)
    return root


def exported(source, tmp_path):
    directory = tmp_path / "artifact"
    document = export_catalog(source, directory, "test.1", require_clean=True)
    return directory, document


def evidence(directory, document):
    report = {
        "schema_version": 1,
        "status": "PASSED",
        "scope": "full-catalog",
        "server_version": "1.0.0-rc.78",
        "source_commit": document["source"]["commit"],
        "catalog_sha256": digest((directory / "catalog.json").read_bytes()),
        "results": [
            {
                "model_id": model["id"],
                **{
                    field: "PASSED"
                    for field in (
                        "registration",
                        "startup",
                        "behavior",
                        "lifecycle",
                        "cleanup",
                    )
                },
            }
            for model in document["models"]
        ],
    }
    path = directory / "qualification-test.json"
    path.write_bytes(json_bytes(report))
    return path, report


def test_export_is_deterministic_and_contains_only_declared_content(source, tmp_path):
    first, document = exported(source, tmp_path)
    second = tmp_path / "second"
    export_catalog(source, second, "test.1", require_clean=True)
    for name in ("catalog.json", "model-files.zip"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert not document["source"]["dirty"]
    paths = {file["path"] for file in document["files"]}
    assert "extensions/ocpp_meter_values.py" in paths
    assert "extensions/thermal_model.py" in paths
    assert not any(
        path.startswith(("spx_mcp/", "installer/", "profiles/")) for path in paths
    )
    assert all(
        "deployment" not in service and "commands" not in service
        for service in document["services"]
    )
    assert verify_catalog(first) == document


@pytest.mark.parametrize("kind", ["file", "zip", "extra", "duplicate"])
def test_artifact_tampering_is_rejected(source, tmp_path, kind):
    directory, document = exported(source, tmp_path)
    record = document["files"][0]
    if kind == "file":
        (directory / "files" / record["path"]).write_bytes(b"changed")
    elif kind == "zip":
        with zipfile.ZipFile(directory / "model-files.zip", "a") as archive:
            archive.writestr("unexpected.py", "print('unexpected')")
    elif kind == "extra":
        (directory / "files/extra.yaml").write_text("attributes: {}", encoding="utf-8")
    else:
        document["files"].append(record)
        (directory / "catalog.json").write_bytes(json_bytes(document))
    with pytest.raises(CatalogError):
        verify_catalog(directory)


@pytest.mark.parametrize(
    "path",
    [
        "../private.env",
        "/absolute.yaml",
        "library/../.env",
        "extensions/../../secret",
        "extensions\\secret.py",
        "LICENSE-secret",
        "spx_mcp/__init__.py",
    ],
)
def test_export_paths_cannot_escape_the_resource_boundary(source, path):
    with pytest.raises(CatalogError):
        safe_file(source, path)


def test_resource_paths_have_one_canonical_archive_name(source):
    with pytest.raises(CatalogError, match="Unsafe catalog path"):
        safe_file(source, "extensions//thermal_model.py", resource=True)


def test_dirty_catalog_is_local_only(source, tmp_path):
    (source / "README.md").write_text("modified", encoding="utf-8")
    document = export_catalog(source, tmp_path / "dirty", "preview.local")
    assert document["source"]["dirty"]
    with pytest.raises(CatalogError, match="clean"):
        build_document(source, "preview.local", require_clean=True)
    with pytest.raises(CatalogError, match="clean"):
        release_manifest(tmp_path / "dirty", "preview", [])


@pytest.mark.parametrize(
    "spec,version,expected",
    [
        ("==1.0.0-rc.78", "v1.0.0-rc.78", True),
        ("==1.0.0-rc.78", "1.0.0-rc.79", False),
        (">=1.1.0,<2.0.0", "1.1.5", True),
        (">=1.1.0,<2.0.0", "1.0.9", False),
        (">=1.1.0,<2.0.0", "2.0.0", False),
        (">=1.0.0-rc.9,<1.0.0", "1.0.0-rc.10", False),
    ],
)
def test_server_version_policy_includes_explicit_rc_semantics(spec, version, expected):
    assert server_matches(spec, version) is expected


def test_reference_selection_matches_pack_protocol_and_server_rules(source):
    document = build_document(source, "test.1")
    selected = select_models(
        document, "1.0.0-rc.78", protocols=["modbus"], pack="industrial_iiot_pack"
    )
    assert selected
    assert all("industrial_iiot_pack" in model["packages"] for model in selected)
    assert all(
        "modbus" in model["protocols"] or not model["protocols"] for model in selected
    )
    assert select_models(document, "1.1.0", protocols=["modbus"]) == []
    with pytest.raises(CatalogError, match="Unknown"):
        select_models(document, "1.0.0-rc.78", protocols=["typo"])


def test_missing_declared_helper_fails_before_export(source):
    path = source / "library/catalog/models.yaml"
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    next(m for m in content["models"] if m["id"] == "Energy.CSMS.Ocpp").pop(
        "distribution"
    )
    path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    with pytest.raises(CatalogError, match="distribution.resources"):
        build_document(source, "test.1")


def test_stable_requires_complete_matching_runtime_evidence(source, tmp_path):
    directory, document = exported(source, tmp_path)
    assert release_manifest(directory, "preview", [])["qualification"] == []
    with pytest.raises(CatalogError, match="Stable requires"):
        release_manifest(directory, "stable", [])
    path, _ = evidence(directory, document)
    manifest = release_manifest(directory, "stable", [path])
    assert manifest["qualification"][0]["sha256"] == digest(path.read_bytes())


@pytest.mark.parametrize(
    "mutation",
    ["hash", "subset", "failed", "scope", "duplicate", "commit", "cleanup", "schema"],
)
def test_invalid_qualification_cannot_promote_to_stable(source, tmp_path, mutation):
    directory, document = exported(source, tmp_path)
    path, report = evidence(directory, document)
    if mutation == "hash":
        report["catalog_sha256"] = "0" * 64
    elif mutation == "subset":
        report["results"].pop()
    elif mutation == "failed":
        report["results"][0]["startup"] = "FAILED"
    elif mutation == "scope":
        report["scope"] = "diagnostic-subset"
    elif mutation == "duplicate":
        report["results"][0] = report["results"][1]
    elif mutation == "commit":
        report["source_commit"] = "0" * 40
    elif mutation == "schema":
        report["schema_version"] = 2
    else:
        report["results"][0]["cleanup"] = "FAILED"
    path.write_bytes(json_bytes(report))
    with pytest.raises(CatalogError):
        release_manifest(directory, "stable", [path])


def test_scaffold_clones_behavior_and_refreshes_generated_indexes(source):
    before = build_document(source, "before")
    path = scaffold(
        source,
        model_id="Community.Thermal.Demo",
        name="community_thermal_demo",
        description="A contributor-specific thermal demonstration",
        packs=["industrial_iiot_pack"],
        copy_from="Process.ThermalController.Advanced",
    )
    definition = yaml.safe_load(path.read_text(encoding="utf-8"))
    original = yaml.safe_load(
        (
            source
            / "library/domains/industrial/controller/generic/thermal_controller_advanced.yaml"
        ).read_text(encoding="utf-8")
    )
    assert definition["actions"] == original["actions"]
    after = build_document(source, "after")
    assert len(after["models"]) == len(before["models"]) + 1
    model = next(m for m in after["models"] if m["id"] == "Community.Thermal.Demo")
    assert "extensions/thermal_model.py" in model["files"]
    assert (
        "Community.Thermal.Demo"
        in next(p for p in after["packs"] if p["id"] == "industrial_iiot_pack")[
            "recommended_model_ids"
        ]
    )
    saved = path.read_bytes()
    with pytest.raises(CatalogError):
        scaffold(
            source,
            model_id="Community.Thermal.Demo",
            name="community_thermal_demo",
            description="duplicate",
            packs=[],
        )
    assert path.read_bytes() == saved


def test_minimal_scaffold_produces_a_valid_catalog_draft(source):
    path = scaffold(
        source,
        model_id="Community.Pt100.Demo",
        name="community_pt100_demo",
        description="Demonstration temperature telemetry",
        packs=["embedded_lab_pack"],
    )
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert model["attributes"]["temperature_c"]["unit"] == "degC"
    assert model["actions"][0]["call"] == "$in(k__temperature_c)"
    assert build_document(source, "draft")["source"]["dirty"]


def test_public_contract_guard_rejects_removed_attributes_and_narrowed_support(source):
    from tools.catalog_compatibility import public_contract_issues

    path = (
        source
        / "library/domains/industrial/controller/generic/thermal_controller_advanced.yaml"
    )
    definition = yaml.safe_load(path.read_text(encoding="utf-8"))
    removed = next(
        name for name in definition["attributes"] if not name.startswith("_")
    )
    definition["attributes"].pop(removed)
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")
    catalog = source / "library/catalog/models.yaml"
    content = yaml.safe_load(catalog.read_text(encoding="utf-8"))
    content["models"][0].setdefault("distribution", {})[
        "server_compatibility"
    ] = ">=1.1.0,<2.0.0"
    catalog.write_text(yaml.safe_dump(content), encoding="utf-8")
    issues = public_contract_issues(source, "HEAD")
    assert any("attributes removed" in issue and removed in issue for issue in issues)
    assert any("previous target" in issue for issue in issues)


def test_unlisted_model_cannot_silently_enter_the_library(source):
    path = source / "library/domains/environment/sensor/generic/unlisted.yaml"
    path.write_text("name: unlisted\nattributes: {value: 1}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="missing from library/catalog/models.yaml"):
        build_document(source, "draft")


def test_clean_export_reads_git_blobs_instead_of_checkout_newlines(source, tmp_path):
    name = (
        "library/domains/industrial/controller/generic/thermal_controller_advanced.yaml"
    )
    committed = subprocess.check_output(
        ["git", "-C", str(source), "show", "HEAD:" + name]
    )
    checkout = tmp_path / "crlf-checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-checkout",
            "--no-hardlinks",
            str(source),
            str(checkout),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "config", "core.autocrlf", "true"], check=True
    )
    subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--quiet", "--force", "HEAD"],
        check=True,
    )
    # The reduced fixture has empty taxonomy/profile directories, which Git
    # does not store. Restore those directories without introducing any files.
    for relative in ("profiles", "library/domains/building", "library/domains/lab"):
        (checkout / relative).mkdir(parents=True, exist_ok=True)
    assert (checkout / name).read_bytes() == committed.replace(b"\n", b"\r\n")
    directory = tmp_path / "eol-artifact"
    document = export_catalog(checkout, directory, "eol", require_clean=True)
    assert not document["source"]["dirty"]
    assert (directory / "files" / name).read_bytes() == committed


def test_explicit_unpublished_draft_is_validated_but_not_exported(source):
    path = "library/domains/environment/sensor/generic/draft.yaml"
    (source / path).write_text(
        "name: draft\nattributes: {value: 1}\n", encoding="utf-8"
    )
    catalog = source / "library/catalog/models.yaml"
    content = yaml.safe_load(catalog.read_text(encoding="utf-8"))
    content["unpublished_models"] = [
        {"path": path, "reason": "Pending behavior review"}
    ]
    catalog.write_text(yaml.safe_dump(content), encoding="utf-8")
    document = build_document(source, "draft")
    assert path not in {file["path"] for file in document["files"]}
    content["unpublished_models"].append(content["unpublished_models"][0])
    catalog.write_text(yaml.safe_dump(content), encoding="utf-8")
    with pytest.raises(CatalogError, match="listed exactly once"):
        build_document(source, "draft")
