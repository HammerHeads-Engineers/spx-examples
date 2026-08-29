# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "installer-smoke.yml"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _job(name: str, next_name: Optional[str] = None) -> str:
    workflow = _workflow()
    start = workflow.index(f"\n  {name}:\n")
    if next_name is None:
        return workflow[start:]
    end = workflow.index(f"\n  {next_name}:\n", start)
    return workflow[start:end]


def test_smoke_workflow_runs_on_pull_requests_and_manual_dispatch() -> None:
    workflow = _workflow()

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert "- develop" in workflow
    assert "permissions:\n  contents: read" in workflow


def test_smoke_workflow_covers_supported_hosted_runner_families() -> None:
    workflow = _workflow()

    for runner in (
        "ubuntu-22.04",
        "ubuntu-24.04",
        "windows-2022",
        "windows-2025",
        "macos-15",
        "macos-15-intel",
    ):
        assert runner in workflow


def test_linux_smoke_builds_and_runs_self_extractor_without_starting_stack() -> None:
    job = _job("linux-installer-smoke", "windows-installer-smoke")

    assert "build_installer_package.sh" in job
    assert "build_self_extractors.sh" in job
    assert "spx-installer-${VERSION}.run" in job
    assert "--allow-missing-product-key" in job
    assert "--no-start" in job
    assert "Exercise the interactive wizard with scripted stdin" in job
    assert 'fake_bin}/docker"' in job
    assert "actions/upload-artifact@v4" in job


def test_windows_smoke_installs_bundle_and_runs_installed_launcher() -> None:
    job = _job("windows-installer-smoke", "macos-installer-smoke")

    assert "packaging\\windows\\Build.ps1" in job
    assert "name: Windows installer smoke" in job
    assert 'ArgumentList @("/quiet", "/norestart"' in job
    assert "%LOCALAPPDATA%\\SPX\\app" in job or '"SPX\\app\\SpxLauncher.exe"' in job
    assert '"setup",' in job
    assert '"--allow-missing-product-key",' in job
    assert '"spx-fake-docker"' in job


def test_macos_smoke_installs_package_and_checks_bundled_python() -> None:
    job = _job("macos-installer-smoke", "full-stack-smoke")

    assert "build_macos_pkg.sh" in job
    assert "installer-macos-${VERSION}.pkg" in job
    assert "-allowUntrusted" in job
    assert "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" in job
    assert 'file "${python_bin}" | grep -q "universal binary"' in job
    assert "pkgutil --pkg-info com.hammerheadsengineers.spx.python" in job
    assert "SPX Tools/SPX Setup.app/Contents/Resources/spx-installer" in job


def test_full_stack_job_is_secret_gated_and_cleans_up() -> None:
    workflow = _workflow()
    job = _job("full-stack-smoke")

    assert 'cron: "17 3 * * *"' in workflow
    assert "inputs.run_full_stack" in job
    assert "secrets.SPX_TEST_PRODUCT_KEY" in job
    assert "docker compose" in job
    assert "spx-start.sh" in job
    assert "tests/packs/industrial_iiot_pack" in job
    assert "if: ${{ always() }}" in job
    assert "docker compose down --remove-orphans --volumes" in job
