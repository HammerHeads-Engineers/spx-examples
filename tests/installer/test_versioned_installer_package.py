# SPDX-License-Identifier: MIT

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "build_installer_package.sh"
SELF_EXTRACTOR_SCRIPT = REPO_ROOT / "scripts" / "build_self_extractors.sh"


def test_package_builder_supports_versioned_release_archives(tmp_path: Path) -> None:
    output_dir = tmp_path / "dist"

    result = subprocess.run(
        [
            "bash",
            str(PACKAGE_SCRIPT),
            "--output-dir",
            str(output_dir),
            "--version",
            "v1.2.3",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "spx-installer-1.2.3.tgz" in result.stdout
    assert (output_dir / "spx-installer-1.2.3.tgz").is_file()
    assert not (output_dir / "spx-installer.tgz").exists()


def test_self_extractors_normalize_tag_versions_in_filenames(tmp_path: Path) -> None:
    output_dir = tmp_path / "dist"

    subprocess.run(
        [
            "bash",
            str(PACKAGE_SCRIPT),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            "bash",
            str(SELF_EXTRACTOR_SCRIPT),
            "--output-dir",
            str(output_dir),
            "--version",
            "v1.2.3",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "spx-installer-1.2.3.run" in result.stdout
    assert "spx-installer-1.2.3.ps1" in result.stdout
    assert (output_dir / "spx-installer-1.2.3.run").is_file()
    assert (output_dir / "spx-installer-1.2.3.ps1").is_file()
    assert not (output_dir / "spx-installer-v1.2.3.run").exists()
    assert not (output_dir / "spx-installer-v1.2.3.ps1").exists()
