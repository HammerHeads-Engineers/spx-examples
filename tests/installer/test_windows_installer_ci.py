# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
LAUNCHER_PATH = REPO_ROOT / "packaging" / "windows" / "launcher" / "Program.cs"
BUNDLE_WXS_PATH = REPO_ROOT / "packaging" / "windows" / "wix" / "SPX.Bundle.wxs"
PRODUCT_WXS_PATH = REPO_ROOT / "packaging" / "windows" / "wix" / "SPX.Product.wxs"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _job(name: str, next_name: Optional[str] = None) -> str:
    workflow = _workflow()
    start = workflow.index(f"\n  {name}:\n")
    if next_name is None:
        return workflow[start:]
    end = workflow.index(f"\n  {next_name}:\n", start)
    return workflow[start:end]


def test_windows_installer_job_runs_after_semantic_release() -> None:
    job = _job("build-windows-installer", "build-macos-installer")

    assert "needs: release" in job
    assert "needs.release.outputs.released == 'true'" in job
    assert "ref: ${{ needs.release.outputs.tag }}" in job
    assert "runs-on: windows-latest" in job


def test_windows_installer_job_provisions_native_build_dependencies() -> None:
    job = _job("build-windows-installer", "build-macos-installer")

    assert "actions/setup-python@v7" in job
    assert 'python-version: "3.12.10"' in job
    assert "actions/setup-dotnet@v6" in job
    assert 'dotnet-version: "8.0.x"' in job
    assert 'dotnet tool install --global wix --version "6.*"' in job
    assert (
        'wix extension add --global "WixToolset.BootstrapperApplications.wixext/$wixVersion"'
        in job
    )
    assert 'wix extension add --global "WixToolset.Util.wixext/$wixVersion"' in job
    assert "wix extension list --global" in job
    assert "poetry install --with=dev --no-root" in job


def test_windows_installer_job_builds_validates_and_publishes_bundle() -> None:
    job = _job("build-windows-installer", "build-macos-installer")

    assert ".\\packaging\\windows\\Build.ps1" in job
    assert 'Filter "spx-installer-*.exe"' in job
    assert "actions/upload-artifact@v7" in job
    assert "gh release upload" in job
    assert "steps.windows_artifact.outputs.path" in job


def test_windows_packaging_docs_describe_ci_artifact() -> None:
    docs_path = REPO_ROOT / "packaging" / "windows" / "README.md"
    docs = docs_path.read_text(encoding="utf-8")

    assert "windows-latest" in docs
    assert "spx-installer-<version>.exe" in docs
    assert "unsigned" in docs
    assert "bundle" in docs


def test_windows_launcher_requires_the_bundled_python_runtime() -> None:
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "Microsoft.Win32" in launcher
    assert "SOFTWARE\\Python\\PythonCore\\" in launcher
    assert "RegistryHive.CurrentUser" in launcher
    assert "RegistryHive.LocalMachine" in launcher
    assert "requiredVersion: (3, 12)" in launcher
    assert "new PythonCandidate" not in launcher
    assert "The bundled Python 3.12 runtime was not found" in launcher


def test_windows_bundle_uses_an_spx_owned_python_marker() -> None:
    bundle = BUNDLE_WXS_PATH.read_text(encoding="utf-8")
    product = PRODUCT_WXS_PATH.read_text(encoding="utf-8")

    assert 'Value="BundledPython312Installed"' in bundle
    assert 'Variable="SpxBundledPython312Installed"' in bundle
    assert 'DetectCondition="SpxBundledPython312Installed = 1"' in bundle
    assert "Python312InstallPathPerMachine OR Python312InstallPathPerUser" not in bundle
    assert 'Name="BundledPython312Installed"' in product
