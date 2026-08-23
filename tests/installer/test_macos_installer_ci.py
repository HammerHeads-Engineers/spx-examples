# SPDX-License-Identifier: MIT

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"


def _macos_job() -> str:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    start = workflow.index("\n  build-macos-installer:\n")
    return workflow[start:]


def test_macos_installer_job_runs_after_semantic_release() -> None:
    job = _macos_job()

    assert "needs: release" in job
    assert "needs.release.outputs.released == 'true'" in job
    assert "ref: ${{ needs.release.outputs.tag }}" in job
    assert "runs-on: macos-latest" in job
    assert "environment: macos-signing" in job


def test_macos_installer_job_builds_signed_native_package() -> None:
    job = _macos_job()

    assert "actions/setup-python@v5" in job
    assert 'python-version: "3.12.10"' in job
    assert '--app-sign "${MACOS_APP_SIGN_IDENTITY}"' in job
    assert '--sign "${MACOS_INSTALLER_SIGN_IDENTITY}"' in job
    assert '--keychain "${MACOS_SIGNING_KEYCHAIN}"' in job
    assert '--notarytool-profile "${MACOS_NOTARY_PROFILE}"' in job
    assert "path=dist/spx-installer-macos-${version}.pkg" in job


def test_macos_installer_job_prepares_ephemeral_signing_keychain() -> None:
    job = _macos_job()

    assert "security create-keychain" in job
    assert "security import" in job
    assert "-f pkcs12" in job
    assert "security set-key-partition-list" in job
    assert "xcrun notarytool store-credentials" in job
    assert '--key-id "${MACOS_NOTARY_KEY_ID}"' in job
    assert '--issuer "${MACOS_NOTARY_ISSUER_ID}"' in job


def test_macos_installer_job_validates_and_publishes_package() -> None:
    job = _macos_job()

    assert (
        'pkgutil --check-signature "${{ steps.macos_package.outputs.path }}"'
        in job
    )
    assert "xcrun stapler validate" in job
    assert "spctl -a -vv -t install" in job
    assert "actions/upload-artifact@v4" in job
    assert "gh release upload" in job
    assert "steps.macos_package.outputs.path" in job
    assert "Clean up macOS signing material" in job


def test_macos_job_publishes_release_tagged_workflow_artifact() -> None:
    job = _macos_job()

    assert "name: spx-installer-${{ needs.release.outputs.tag }}-macos" in job
    assert 'gh release upload "${{ needs.release.outputs.tag }}"' in job


def test_macos_release_docs_describe_ci_artifact() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "macos-latest" in readme
    assert "spx-installer-macos-<version>.pkg" in readme
    assert "signed, notarized, and stapled package" in readme
