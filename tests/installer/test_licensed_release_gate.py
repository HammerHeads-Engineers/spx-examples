"""Required licensed stack qualification must gate release publication."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_required_installer_checks_cannot_pass_by_skipping() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/installer-stack-qualification.yml").read_text())
    steps = workflow["jobs"]["full-stack-smoke"]["steps"]
    required = next(step for step in steps if step["name"] == "Require installed starter and PLC integration tests")
    assert "python -m tools.required_pytest" in required["run"]
    assert "test_pack_instances_running.py" in required["run"]
    assert "test_modbus_master_plc_demo_smoke.py" in required["run"]


def test_release_requires_licensed_stack_qualification() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci-cd.yml").read_text())
    jobs = workflow["jobs"]
    release = jobs["release"]
    assert "installer-stack-qualification" in release["needs"]
    assert "needs.installer-stack-qualification.result == 'success'" in release["if"]
    qualification = jobs["installer-stack-qualification"]
    assert qualification["uses"] == "./.github/workflows/installer-stack-qualification.yml"
    assert qualification["secrets"]["SPX_TEST_PRODUCT_KEY"] == "${{ secrets.SPX_TEST_PRODUCT_KEY }}"


def test_licensed_stack_artifacts_exclude_unredacted_generated_configuration() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/installer-stack-qualification.yml").read_text())
    steps = workflow["jobs"]["full-stack-smoke"]["steps"]
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert "spx-full-generated" not in upload["with"]["path"]
    redact_index = next(index for index, step in enumerate(steps) if step["name"] == "Redact diagnostic files")
    assert redact_index < steps.index(upload)


def test_diagnostic_redaction_removes_key_before_upload(tmp_path, monkeypatch) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/installer-stack-qualification.yml").read_text())
    steps = workflow["jobs"]["full-stack-smoke"]["steps"]
    redact = next(step for step in steps if step["name"] == "Redact diagnostic files")
    script = redact["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    key = "FAKE-TEST-KEY-DO-NOT-EXPOSE"
    monkeypatch.setenv("SPX_PRODUCT_KEY", key)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    log = tmp_path / "spx-full-start.log"
    log.write_text("startup " + key + "\n", encoding="utf-8")
    exec(compile(script, "workflow-diagnostic-redaction", "exec"), {})
    assert log.read_text(encoding="utf-8") == "startup [REDACTED]\n"
