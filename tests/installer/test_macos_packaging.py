# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("bash") is None, reason="Requires Bash")
@pytest.mark.parametrize("stop_exit", [0, 1])
def test_cleanup_retains_files_until_stack_stop_succeeds(tmp_path, stop_exit):
    source = (ROOT / "installer/macos/spx_cleanup_launcher.applescript").read_text()
    body = source.split("on cleanupShell", 1)[1].split("end cleanupShell", 1)[0]
    # Run the launcher's actual static shell lines with test-owned directories.
    lines = [
        json.loads(match.group(1))
        for line in body.splitlines()
        if (match := re.fullmatch(r'\s*set end of commandLines to (".*")', line))
    ]
    generated, runtime = tmp_path / "generated", tmp_path / "runtime"
    generated.mkdir()
    runtime.mkdir()
    helper = generated / "spx-stop.sh"
    helper.write_text(f"#!/bin/sh\nexit {stop_exit}\n")
    helper.chmod(0o755)
    result = subprocess.run(
        [shutil.which("bash"), "-c", "\n".join(lines)],
        env={
            **os.environ,
            "GENERATED_DIR": str(generated),
            "RUNTIME_DIR": str(runtime),
        },
        capture_output=True,
        text=True,
    )
    assert bool(result.returncode) == bool(stop_exit)
    assert generated.exists() == bool(stop_exit)
    assert runtime.exists() == bool(stop_exit)
    if stop_exit:
        assert "generated files were retained" in result.stderr


def test_native_macos_package_flow_contains_launchers_license_and_notarization() -> (
    None
):
    package_script = (ROOT / "scripts/build_macos_pkg.sh").read_text(encoding="utf-8")
    assert "pkgbuild" in package_script
    assert "productbuild" in package_script
    assert "--app-sign" in package_script
    assert "--notarytool-profile" in package_script
    assert "notarize_package" in package_script
    assert r'"\${COMMAND_LINE_INSTALL:-}"' in package_script
    assert r'"\${SPX_SKIP_AUTO_SETUP:-}"' in package_script
    assert "Installer.app/Contents/MacOS/Installer" in package_script
    assert r'/bin/launchctl bootstrap "gui/\${console_uid}"' in package_script
    assert r'launchctl bootstrap "gui/\${console_uid}"' in package_script
    assert "launchctl asuser" not in package_script
    assert (ROOT / "packaging/macos/resources/English.lproj/License.rtf").is_file()
    for name in (
        "spx_setup_launcher.applescript",
        "spx_start_launcher.applescript",
        "spx_stop_launcher.applescript",
        "spx_cleanup_launcher.applescript",
        "spx_uninstall_launcher.applescript",
    ):
        assert (ROOT / "installer/macos" / name).is_file()


def test_macos_postinstall_repairs_only_root_owned_runtime_parent() -> None:
    package_script = (ROOT / "scripts/build_macos_pkg.sh").read_text(encoding="utf-8")

    assert (
        r'support_dir="\${console_home}/Library/Application Support/SPX"'
        in package_script
    )
    assert r'if [[ "\${support_owner}" == "root" ]]; then' in package_script
    assert (
        r'/usr/sbin/chown "\${console_user}:\${user_group}" "\${support_dir}"'
        in package_script
    )
    assert r'helper="\${launch_agents_dir}/\${label}.sh"' in package_script
    assert (
        r'/usr/sbin/chown "\${console_user}:\${user_group}" "\${launch_agents_dir}"'
        in package_script
    )
    assert "Application Support/SPX/\\${label}.sh" not in package_script
    assert "/usr/sbin/chown -R" not in package_script
    assert "chown -R" not in package_script
    assert r'/bin/launchctl bootstrap "gui/\${console_uid}"' in package_script


def test_macos_setup_command_only_pauses_when_setup_fails() -> None:
    launcher = (ROOT / "spx-setup.command").read_text(encoding="utf-8")

    assert 'if [ "$EXIT_CODE" -ne 0 ]; then' in launcher
    assert 'read -r -p "Press Enter to close..." _ || true' in launcher


def test_macos_cleanup_preserves_docker_data_and_unrelated_processes() -> None:
    for name in (
        "spx_cleanup_launcher.applescript",
        "spx_uninstall_launcher.applescript",
    ):
        content = (ROOT / "installer/macos" / name).read_text(encoding="utf-8")
        assert "--remove-orphans" not in content
        assert "--volumes" not in content
        assert "--rmi all" not in content
        assert "pkill -f spx-ble-adapter" not in content


def test_macos_uninstaller_elevates_filesystem_cleanup_after_user_stack_stop() -> None:
    content = (ROOT / "installer/macos/spx_uninstall_launcher.applescript").read_text(
        encoding="utf-8"
    )
    cleanup_start = content.index("on cleanupShell")
    uninstall_start = content.index("on uninstallShell")
    cleanup_shell = content[cleanup_start:uninstall_start]
    uninstall_shell = content[uninstall_start:]

    assert r"\"$GENERATED_DIR/spx-stop.sh\" || true" in cleanup_shell
    assert r"rm -rf \"$SUPPORT_DIR\"" not in cleanup_shell
    assert r"rm -rf \"$SUPPORT_DIR\"" in uninstall_shell
    assert "with administrator privileges" in content
    assert "uninstallShell(appsDirPath, packageId, supportDir" in content
