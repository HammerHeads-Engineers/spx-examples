# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
NIGHTLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-nightly.yml"


def _workflow(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _job(workflow: str, name: str, next_name: Optional[str] = None) -> str:
    start = workflow.index(f"\n  {name}:\n")
    if next_name is None:
        return workflow[start:]
    end = workflow.index(f"\n  {next_name}:\n", start)
    return workflow[start:end]


def test_pr_tests_are_limited_to_supported_boundary_and_bundled_python() -> None:
    workflow = _workflow(CI_WORKFLOW_PATH)
    job = _job(workflow, "tests", "core-integration")

    assert "python-version: [3.9.19, 3.12.10]" in job
    assert "3.10.14" not in job
    assert "3.11.9" not in job
    assert "cache: poetry" in job
    assert job.index("- name: Install Poetry") < job.index("- name: Set up Python")
    assert "tests/core/unit" in job
    assert "tests/installer" in job
    assert "tests/mcp/unit" in job
    assert "tests/packs/*/unit" in job
    assert "docker compose" not in job
    assert "SPX_PRODUCT_KEY" not in job
    assert "poetry run pytest -q\n" not in job


def test_core_integration_is_a_separate_parallel_python_312_job() -> None:
    workflow = _workflow(CI_WORKFLOW_PATH)
    job = _job(workflow, "core-integration", "pack-tests")

    assert "needs: pr-title-gate" in job
    assert "python-version: 3.12.10" in job
    assert "cache: poetry" in job
    assert job.index("- name: Install Poetry") < job.index("- name: Set up Python 3.12.10")
    assert "docker compose up -d" in job
    assert "tests/core/integration" in job
    assert "tests" not in job.split("needs:", 1)[0]


def test_pack_tests_run_in_parallel_without_full_embedded_pack() -> None:
    workflow = _workflow(CI_WORKFLOW_PATH)
    job = _job(workflow, "pack-tests", "embedded-lab-smoke")

    assert "needs: pr-title-gate" in job
    assert "needs: tests" not in job
    assert "python-version: 3.12.10" in job
    assert job.index("- name: Install Poetry") < job.index("- name: Set up Python")
    for pack in ("industrial_iiot_pack", "energy_pack", "smart_building_pack"):
        assert pack in job
    assert "embedded_lab_pack" not in job
    assert "cache: poetry" in job


def test_embedded_smoke_runs_only_the_two_representative_tests() -> None:
    workflow = _workflow(CI_WORKFLOW_PATH)
    job = _job(workflow, "embedded-lab-smoke", "release")

    assert "needs: pr-title-gate" in job
    assert "python-version: 3.12.10" in job
    assert job.index("- name: Install Poetry") < job.index("- name: Set up Python 3.12.10")
    assert "test_scpi_ascii_port_override.py" in job
    assert "test_modbus_prevac_bcu14_smoke.py" in job
    assert "poetry run pytest -q tests/packs/embedded_lab_pack" not in job
    assert "tests/packs/embedded_lab_pack --" not in job


def test_release_requires_all_fast_jobs_and_only_runs_on_main_branches() -> None:
    workflow = _workflow(CI_WORKFLOW_PATH)
    job = _job(workflow, "release", "build-windows-installer")

    assert "needs: [tests, core-integration, pack-tests, embedded-lab-smoke]" in job
    assert "github.ref == 'refs/heads/develop'" in job
    assert "github.ref == 'refs/heads/main'" in job
    for required_job in (
        "needs.tests.result == 'success'",
        "needs.core-integration.result == 'success'",
        "needs.pack-tests.result == 'success'",
        "needs.embedded-lab-smoke.result == 'success'",
    ):
        assert required_job in job


def test_nightly_keeps_full_python_compatibility_and_embedded_validation() -> None:
    workflow = _workflow(NIGHTLY_WORKFLOW_PATH)
    compatibility = _job(workflow, "python-compatibility", "embedded-lab-full")
    embedded = _job(workflow, "embedded-lab-full")

    assert 'cron: "17 3 * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    for version in ("3.9.19", "3.10.14", "3.11.9", "3.12.10"):
        assert version in compatibility
    assert "docker compose" not in compatibility
    assert "tests/core/unit" in compatibility
    assert "tests/packs/*/unit" in compatibility
    assert "python-version: 3.12.10" in embedded
    assert embedded.index("- name: Install Poetry") < embedded.index("- name: Set up Python 3.12.10")
    assert "tests/packs/embedded_lab_pack --durations=20" in embedded
    assert "SPX_PRODUCT_KEY" in embedded
    assert "semantic-release" not in workflow
    assert "gh release upload" not in workflow
