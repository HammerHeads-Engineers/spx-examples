# SPDX-License-Identifier: MIT

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_release_exposes_tag_and_release_status_to_artifact_jobs() -> None:
    workflow = _workflow()

    assert '    tags:\n      - "*"' not in workflow
    assert "released: ${{ steps.release_result.outputs.released }}" in workflow
    assert "tag: ${{ steps.release_result.outputs.tag }}" in workflow
    assert "id: release_result" in workflow
    assert 'echo "released=true" >> "$GITHUB_OUTPUT"' in workflow


def test_package_upload_fails_on_http_errors() -> None:
    workflow = _workflow()

    assert "set -euo pipefail" in workflow
    assert "curl --fail-with-body --silent --show-error --retry 3" in workflow
    assert "PACKAGES_TOKEN: ${{ github.token }}" in workflow


def test_release_verification_requires_all_platform_assets() -> None:
    workflow = _workflow()
    start = workflow.index("\n  release-verification:\n")
    verification = workflow[start:]

    assert "needs: [release, build-windows-installer, build-macos-installer]" in verification
    assert '"spx-installer.tgz"' in verification
    assert '"spx-installer-${RELEASE_TAG}.run"' in verification
    assert '"spx-installer-${RELEASE_TAG}.ps1"' in verification
    assert '"spx-installer-${version}.exe"' in verification
    assert '"spx-installer-macos-${version}.pkg"' in verification
