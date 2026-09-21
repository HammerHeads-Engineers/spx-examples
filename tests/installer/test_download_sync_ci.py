# SPDX-License-Identifier: MIT

import os
import subprocess
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
MANUAL_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "sync-release-to-www.yml"
SCRIPT_PATH = REPO_ROOT / "tools" / "sync_release_to_www.sh"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _manual_workflow() -> str:
    return MANUAL_WORKFLOW_PATH.read_text(encoding="utf-8")


def _job(workflow: str, name: str, next_name: Optional[str] = None) -> str:
    start = workflow.index(f"\n  {name}:\n")
    if next_name is None:
        return workflow[start:]
    end = workflow.index(f"\n  {next_name}:\n", start)
    return workflow[start:end]


def _run_sync_script(tmp_path: Path, fake_curl_body: str, **environment: str) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${CURL_LOG}\"\n"
        f"{fake_curl_body}\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "CURL_LOG": str(curl_log),
            "SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED": "true",
            "SPX_WWW_DOWNLOAD_SYNC_ENABLED": "true",
            "SPX_WWW_STAGING_DOWNLOAD_SYNC_URL": "https://staging.example.test/sync",
            "SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN": "staging-secret",
            "SPX_WWW_DOWNLOAD_SYNC_URL": "https://production.example.test/sync",
            "SPX_WWW_DOWNLOAD_SYNC_TOKEN": "production-secret",
            **environment,
        }
    )
    return subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--repository",
            "HammerHeads-Engineers/spx-examples",
            "--tag",
            "v1.1.0-rc.62",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_sync_is_a_downstream_job_after_complete_asset_verification() -> None:
    workflow = _workflow()
    verification = _job(workflow, "release-verification", "sync-release-to-www")
    sync_job = _job(workflow, "sync-release-to-www")

    assert "needs: [release, build-windows-installer, build-macos-installer]" in verification
    assert 'gh release view "${RELEASE_TAG}" --repo "${GITHUB_REPOSITORY}"' in verification
    assert "needs: [release, release-verification]" in sync_job
    assert "needs.release-verification.result == 'success'" in sync_job
    assert "bash tools/sync_release_to_www.sh" in sync_job


def test_release_sync_configures_both_environments_and_safe_rollout_switch() -> None:
    workflow = _workflow()
    sync_job = _job(workflow, "sync-release-to-www")

    for name in (
        "SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED",
        "SPX_WWW_DOWNLOAD_SYNC_ENABLED",
        "SPX_WWW_STAGING_DOWNLOAD_SYNC_URL",
        "SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN",
        "SPX_WWW_DOWNLOAD_SYNC_URL",
        "SPX_WWW_DOWNLOAD_SYNC_TOKEN",
    ):
        assert name in sync_job


def test_sync_script_builds_idempotent_payload_and_notifies_both_targets(tmp_path: Path) -> None:
    result = _run_sync_script(tmp_path, "exit 0")
    log = (tmp_path / "curl.log").read_text(encoding="utf-8")
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert log.count('"event":"release_assets_ready"') == 2
    assert log.count('"repository":"HammerHeads-Engineers/spx-examples"') == 2
    assert log.count('"tag":"v1.1.0-rc.62"') == 2
    assert log.count('"assets_ready":true') == 2
    assert "Authorization: Bearer staging-secret" in log
    assert "Authorization: Bearer production-secret" in log
    assert "Idempotency-Key: HammerHeads-Engineers/spx-examples:v1.1.0-rc.62" in log
    assert "staging.example.test" in log
    assert "production.example.test" in log
    assert "--retry 3" in script
    assert "--connect-timeout 10" in script
    assert "--max-time 60" in script
    assert "staging-secret" not in result.stdout + result.stderr
    assert "production-secret" not in result.stdout + result.stderr


def test_sync_script_attempts_second_target_when_first_fails(tmp_path: Path) -> None:
    result = _run_sync_script(
        tmp_path,
        'if [[ "$*" == *"staging.example.test"* ]]; then exit 22; fi\nexit 0',
    )
    log = (tmp_path / "curl.log").read_text(encoding="utf-8")

    assert result.returncode == 1
    assert "staging.example.test" in log
    assert "production.example.test" in log
    assert "SPX WWW staging sync failed" in result.stderr


def test_sync_script_skips_cleanly_until_integration_is_enabled(tmp_path: Path) -> None:
    result = _run_sync_script(
        tmp_path,
        "exit 99",
        SPX_WWW_DOWNLOAD_SYNC_ENABLED="false",
        SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED="false",
        SPX_WWW_STAGING_DOWNLOAD_SYNC_URL="",
        SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN="",
        SPX_WWW_DOWNLOAD_SYNC_URL="",
        SPX_WWW_DOWNLOAD_SYNC_TOKEN="",
    )

    assert result.returncode == 0
    assert "sync is disabled" in result.stdout
    assert not (tmp_path / "curl.log").exists()


def test_sync_script_requires_configuration_for_each_enabled_target(tmp_path: Path) -> None:
    result = _run_sync_script(
        tmp_path,
        "exit 0",
        SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN="",
    )

    assert result.returncode == 1
    assert "SPX_WWW_STAGING_DOWNLOAD_SYNC_TOKEN" in result.stderr
    assert "staging-secret" not in result.stdout + result.stderr
    assert "production-secret" not in result.stdout + result.stderr


def test_sync_script_supports_staging_only_rollout(tmp_path: Path) -> None:
    result = _run_sync_script(
        tmp_path,
        "exit 0",
        SPX_WWW_STAGING_DOWNLOAD_SYNC_ENABLED="true",
        SPX_WWW_DOWNLOAD_SYNC_ENABLED="false",
        SPX_WWW_DOWNLOAD_SYNC_URL="",
        SPX_WWW_DOWNLOAD_SYNC_TOKEN="",
    )
    log = (tmp_path / "curl.log").read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "staging.example.test" in log
    assert "production.example.test" not in log


def test_manual_sync_workflow_supports_release_replay() -> None:
    workflow = _manual_workflow()
    verification = _job(workflow, "verify-release", "sync-release-to-www")
    sync_job = _job(workflow, "sync-release-to-www")

    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow
    assert "gh release view \"${RELEASE_TAG}\"" in verification
    for asset in (
        '"spx-installer-${version}.tgz"',
        '"spx-installer-${version}.run"',
        '"spx-installer-${version}.ps1"',
        '"spx-installer-${version}.exe"',
        '"spx-installer-macos-${version}.pkg"',
    ):
        assert asset in verification
    assert "needs: verify-release" in sync_job
    assert "bash tools/sync_release_to_www.sh" in sync_job
