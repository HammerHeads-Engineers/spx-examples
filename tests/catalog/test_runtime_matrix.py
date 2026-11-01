import pytest

from tools.model_catalog import CatalogError, export_catalog, json_bytes
from tools.runtime_policy import check_reports
from tools.runtime_targets import plan_targets
from tests.catalog.test_distribution import baseline, source, evidence


def tags(*names):
    return [{"name": name, "digest": "sha256:" + "a" * 64} for name in names]


def test_matrix_freezes_latest_stable_rc_and_retains_older_declared_target():
    matrix = plan_targets(
        tags(
            "latest",
            "v0.2.0",
            "v0.1.0",
            "v1.0.0-rc.78",
            "v1.0.0-rc.79",
            "v1.0.0-alpha.100",
        ),
        ["1.0.0-rc.78"],
        "simplephysx/spx-server",
    )
    rows = matrix["include"]
    assert [(r["channel"], r["version"], r["qualifying"]) for r in rows] == [
        ("stable", "0.2.0", False),
        ("rc", "1.0.0-rc.79", False),
        ("declared", "1.0.0-rc.78", True),
    ]
    assert all("@sha256:" in row["image"] for row in rows)


def test_latest_rc_also_serves_the_matching_declared_target():
    rows = plan_targets(
        tags("v0.2.0", "v1.0.0-rc.78"), ["1.0.0-rc.78"], "simplephysx/spx-server"
    )["include"]
    assert len(rows) == 2
    assert rows[1]["qualifying"]


@pytest.mark.parametrize(
    "available,declared",
    [
        (tags("v1.0.0-rc.78"), ["1.0.0-rc.78"]),
        (tags("v0.2.0", "v1.0.0-rc.79"), ["1.0.0-rc.78"]),
    ],
)
def test_missing_channel_or_declared_image_is_not_substituted(available, declared):
    with pytest.raises(CatalogError):
        plan_targets(available, declared, "simplephysx/spx-server")


def test_failed_advisory_probe_is_visible_without_claiming_unsupported_compatibility(
    source, tmp_path
):
    directory = tmp_path / "artifact"
    document = export_catalog(source, directory, "matrix")
    matrix = plan_targets(
        tags("v0.2.0", "v1.0.0-rc.78"), ["1.0.0-rc.78"], "simplephysx/spx-server"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    path, report = evidence(directory, document)
    report["excluded_models"] = []
    report["environment"] = {"server_image": matrix["include"][1]["image"]}
    required = reports / "qualification-1.0.0-rc.78.json"
    required.write_bytes(json_bytes(report))
    (reports / "probe-stable-0.2.0.json").write_bytes(
        json_bytes({"status": "FAILED", "results": []})
    )
    result = check_reports(directory, matrix, reports)
    assert result["status"] == "PASSED"
    assert result["rows"][0]["status"] == "FAILED"
    assert result["rows"][1]["status"] == "PASSED"
    report["results"].pop()
    required.write_bytes(json_bytes(report))
    assert check_reports(directory, matrix, reports)["status"] == "FAILED"


@pytest.mark.parametrize("mutation", ["source", "hash", "image", "scope", "cleanup"])
def test_required_runtime_evidence_must_match_the_exact_candidate(
    source, tmp_path, mutation
):
    directory = tmp_path / "artifact"
    document = export_catalog(source, directory, "matrix")
    matrix = plan_targets(
        tags("v0.2.0", "v1.0.0-rc.78"), ["1.0.0-rc.78"], "simplephysx/spx-server"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    _, report = evidence(directory, document)
    report.update(
        excluded_models=[], environment={"server_image": matrix["include"][1]["image"]}
    )
    if mutation == "source":
        report["source_commit"] = "0" * 40
    elif mutation == "hash":
        report["catalog_sha256"] = "0" * 64
    elif mutation == "image":
        report["environment"]["server_image"] = "wrong"
    elif mutation == "scope":
        report["scope"] = "compatibility-probe"
    else:
        report["results"][0]["cleanup"] = "FAILED"
    (reports / "qualification-1.0.0-rc.78.json").write_bytes(json_bytes(report))
    assert check_reports(directory, matrix, reports)["status"] == "FAILED"
