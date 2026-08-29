# SPDX-License-Identifier: MIT

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
MACOS_PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "build_macos_pkg.sh"
MACOS_SETUP_APP_SCRIPT = REPO_ROOT / "scripts" / "build_macos_setup_app.sh"
MACOS_NOTARIZATION_SCRIPT = REPO_ROOT / "scripts" / "macos_notarization.sh"


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
    assert '--python-version "3.12.10"' in job


def test_macos_package_bundles_verified_universal_python_runtime() -> None:
    script = MACOS_PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert 'if [[ "${OUTPUT_DIR}" = /* ]]; then' in script
    assert 'DEST_DIR="${OUTPUT_DIR}"' in script
    assert "python-${PYTHON_VERSION}-macos11.pkg" in script
    assert "8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4" in script
    assert "pkgutil --expand-full" in script
    assert "Python_Framework.pkg/Payload" in script
    assert "com.hammerheadsengineers.spx.python" in script
    assert "Library/Frameworks/Python.framework" in script
    assert '--install-location "/Library/Frameworks/Python.framework"' in script
    assert "codesign --verify --deep --strict" in script
    assert "python_version" in script
    assert "--exclude '._*'" in script
    assert '"${python_scripts_dir}/postinstall"' in script
    assert '--scripts "${python_scripts_dir}"' in script
    assert 'python_pkgbuild_args+=(--sign "${SIGN_IDENTITY}")' in script
    assert 'python_pkgbuild_args+=(--keychain "${KEYCHAIN_PATH}")' in script
    assert "--python-version" in script
    assert "--python-package" in script
    assert "find \"${PYTHON_FRAMEWORK_ROOT}\" -type f -name '*.o' -print" in script
    assert 'rm -f "${object_path}"' in script
    assert "Bundled Python runtime contains an unsupported object file" in script
    assert (
        'local python_library="${PYTHON_FRAMEWORK_ROOT}/Versions/${PYTHON_FRAMEWORK_VERSION}/Python"'
        in script
    )
    assert 'codesign "${python_codesign_args[@]}" "${python_library}"' in script
    assert 'codesign --force --sign - "${python_library}"' in script
    assert 'codesign --verify --strict --verbose=2 "${python_library}"' in script
    assert 'pkgutil --check-signature "${COMPONENT_PKG_PATH}"' in script
    assert 'pkgutil --check-signature "${PYTHON_COMPONENT_PKG_PATH}"' in script


def test_native_macos_setup_payload_marks_bundled_python_requirement() -> None:
    package_script = MACOS_PACKAGE_SCRIPT.read_text(encoding="utf-8")
    setup_app_script = MACOS_SETUP_APP_SCRIPT.read_text(encoding="utf-8")

    assert "--native-macos-runtime" in package_script
    assert "NATIVE_MACOS_RUNTIME=0" in setup_app_script
    assert (
        'touch "${RESOURCE_PAYLOAD_DIR}/.spx-macos-bundled-python"' in setup_app_script
    )


def test_macos_notarization_reports_apple_log_before_stapling() -> None:
    script = MACOS_NOTARIZATION_SCRIPT.read_text(encoding="utf-8")

    assert "notarytool" in script
    assert "log" in script
    assert "--output-format json" in script
    assert (
        'if [[ "${notarytool_exit}" -ne 0 || "${notary_status}" != "Accepted" ]]'
        in script
    )
    assert 'echo "Apple notarization report:" >&2' in script
    assert script.index("return 1") < script.index(
        'xcrun stapler staple "${package_path}"'
    )


@pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash is required for the shell flow test"
)
def test_macos_notarization_does_not_staple_an_invalid_submission(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    xcrun = fake_bin / "xcrun"
    xcrun.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "notarytool" && "$2" == "submit" ]]; then
  echo "  id: test-submission"
  echo "  status: Invalid"
elif [[ "$1" == "notarytool" && "$2" == "log" ]]; then
  echo '{"status":"Invalid","issues":[{"message":"The binary is not signed."}]}'
elif [[ "$1" == "stapler" ]]; then
  echo "stapler must not be called for an invalid submission" >&2
  exit 42
else
  echo "unexpected xcrun invocation: $*" >&2
  exit 43
fi
""",
        encoding="utf-8",
    )
    xcrun.chmod(0o755)
    harness = tmp_path / "harness.sh"
    harness.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
source "$1"
if notarize_package "$2" "$3" "test-profile" ""; then
  echo "invalid submission unexpectedly succeeded" >&2
  exit 44
fi
""",
        encoding="utf-8",
    )
    harness.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [
            "bash",
            str(harness),
            str(MACOS_NOTARIZATION_SCRIPT),
            str(tmp_path / "installer.pkg"),
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Apple notarization report:" in result.stderr
    assert "The binary is not signed." in result.stderr
    assert "stapler must not be called" not in result.stderr


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

    assert 'pkgutil --check-signature "${{ steps.macos_package.outputs.path }}"' in job
    assert "pkgutil --expand-full" in job
    assert "name '*-python-component.pkg'" in job
    assert "find \"${inspection_dir}\" -type f -name '*.o' -print" in job
    assert 'pkgutil --check-signature "${python_component}"' not in job
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
