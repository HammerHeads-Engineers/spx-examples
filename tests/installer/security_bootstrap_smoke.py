# SPDX-License-Identifier: MIT
"""Opt-in network smoke: clean install, vulnerable venv and matching cache stamp.

Run with an already patched Python: python tests/installer/security_bootstrap_smoke.py.
Old packages are downloaded by patched pip and installed offline, never used online.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from installer import runtime_bootstrap as runtime  # noqa: E402


def main():
    runtime.verify_environment(Path(sys.executable))
    with tempfile.TemporaryDirectory(prefix="spx-security-") as directory:
        root = Path(directory)
        wheelhouse = root / "wheels"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "download",
                "--no-deps",
                "--only-binary=:all:",
                "-d",
                str(wheelhouse),
                "pip==25.0.1",
                "certifi==2025.8.3",
            ],
            check=True,
        )
        python = runtime.ensure_runtime(root / "venv", ["colorama"])
        fresh = runtime.verify_environment(python)
        stamp = root / "venv" / ".spx-runtime.json"
        before = stamp.read_bytes()
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--no-index",
                "--no-deps",
                "--find-links",
                str(wheelhouse),
                "pip==25.0.1",
                "certifi==2025.8.3",
            ],
            check=True,
        )
        assert runtime.environment_versions(python)["pip"] == "25.0.1"
        assert runtime.ensure_runtime(root / "venv", ["colorama"]) == python
        upgraded = runtime.verify_environment(python)
        assert stamp.read_bytes() == before
        assert runtime.ensure_runtime(root / "venv", ["colorama"]) == python
        reused = runtime.verify_environment(python)
        print(
            json.dumps(
                {
                    "fresh": fresh,
                    "upgrade_with_matching_stamp": upgraded,
                    "reuse": reused,
                    "stamp_preserved": True,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
