# SPDX-License-Identifier: MIT

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"


def _macos_job() -> str:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    start = workflow.index("\n  build-macos-installer:\n")
    return workflow[start:]


def test_macos_installer_job_runs_only_for_release_tags() -> None:
    job = _macos_job()

    assert "needs: [pack-tests, build-installer]" in job
    assert "if: startsWith(github.ref, 'refs/tags/')" in job
    assert "runs-on: macos-latest" in job


def test_macos_installer_job_builds_native_package() -> None:
    job = _macos_job()

    assert "actions/setup-python@v5" in job
    assert 'python-version: "3.12.10"' in job
    assert "scripts/build_macos_pkg.sh --version" in job
    assert "path=dist/spx-installer-macos-${version}.pkg" in job


def test_macos_installer_job_validates_and_publishes_package() -> None:
    job = _macos_job()

    assert "pkgutil --check-signature" in job
    assert "actions/upload-artifact@v4" in job
    assert "gh release upload" in job
    assert "steps.macos_package.outputs.path" in job


def test_macos_release_docs_describe_ci_artifact() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "macos-latest" in readme
    assert "spx-installer-macos-<version>.pkg" in readme
    assert "unsigned package" in readme
