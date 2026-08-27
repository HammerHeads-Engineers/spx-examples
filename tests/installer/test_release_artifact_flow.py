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


def test_release_does_not_use_unsupported_generic_packages_endpoint() -> None:
    workflow = _workflow()

    assert "packages: write" not in workflow
    assert "Publish installer to GitHub Packages" not in workflow
    assert "packages/generic" not in workflow


def test_release_verification_requires_all_platform_assets() -> None:
    workflow = _workflow()
    start = workflow.index("\n  release-verification:\n")
    verification = workflow[start:]

    assert "needs: [release, build-windows-installer, build-macos-installer]" in verification
    assert 'gh release view "${RELEASE_TAG}" --repo "${GITHUB_REPOSITORY}"' in verification
    assert '"spx-installer-${version}.tgz"' in verification
    assert '"spx-installer-${version}.run"' in verification
    assert '"spx-installer-${version}.ps1"' in verification
    assert '"spx-installer-${version}.exe"' in verification
    assert '"spx-installer-macos-${version}.pkg"' in verification


def test_release_build_uses_one_versioned_filename_convention() -> None:
    workflow = _workflow()

    assert 'version="${tag#v}"' in workflow
    assert 'scripts/build_installer_package.sh --package-name "spx-installer" --version "${version}"' in workflow
    assert 'scripts/build_self_extractors.sh --version "${version}"' in workflow
    assert '"dist/spx-installer-${version}.tgz"' in workflow
    assert '"dist/spx-installer-${version}.run"' in workflow
    assert '"dist/spx-installer-${version}.ps1"' in workflow
