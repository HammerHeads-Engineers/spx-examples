# SPDX-License-Identifier: MIT

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"


def _windows_job() -> str:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    start = workflow.index("\n  build-windows-installer:\n")
    end = workflow.index("\n  release:\n", start)
    return workflow[start:end]


def test_windows_installer_job_runs_only_for_release_tags() -> None:
    job = _windows_job()

    assert "needs: [pack-tests, build-installer]" in job
    assert "if: startsWith(github.ref, 'refs/tags/')" in job
    assert "runs-on: windows-latest" in job


def test_windows_installer_job_provisions_native_build_dependencies() -> None:
    job = _windows_job()

    assert "actions/setup-python@v5" in job
    assert 'python-version: "3.12.10"' in job
    assert "actions/setup-dotnet@v4" in job
    assert 'dotnet-version: "8.0.x"' in job
    assert 'dotnet tool install --global wix --version "6.*"' in job
    assert "poetry install --with=dev --no-root" in job


def test_windows_installer_job_builds_validates_and_publishes_bundle() -> None:
    job = _windows_job()

    assert ".\\packaging\\windows\\Build.ps1" in job
    assert 'Filter "spx-installer-*.exe"' in job
    assert "actions/upload-artifact@v4" in job
    assert "gh release upload" in job
    assert "steps.windows_artifact.outputs.path" in job


def test_windows_packaging_docs_describe_ci_artifact() -> None:
    docs_path = REPO_ROOT / "packaging" / "windows" / "README.md"
    docs = docs_path.read_text(encoding="utf-8")

    assert "windows-latest" in docs
    assert "spx-installer-<version>.exe" in docs
    assert "unsigned bundle" in docs
