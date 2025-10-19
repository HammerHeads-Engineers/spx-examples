# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import os
import pathlib
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


def _server_healthy(url: str, timeout: int = 5) -> bool:
    """Quick health probe; returns True if server responds without 5xx."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def discover_examples():
    """Find runnable example scripts under examples/.

    You can restrict which scripts run by setting SPX_EXAMPLES_ONLY
    to a comma-separated list of paths relative to examples/ (e.g.,
    "01-hello-world.py,first_simulation.py").
    """
    if not EXAMPLES_DIR.exists():
        return []

    only = os.environ.get("SPX_EXAMPLES_ONLY")
    if only:
        paths = [EXAMPLES_DIR / p.strip() for p in only.split(",") if p.strip()]
        return [p for p in paths if p.exists() and p.suffix == ".py"]

    candidates = []
    for path in EXAMPLES_DIR.glob("**/*.py"):
        name = path.name.lower()
        if name in ("__init__.py",):
            continue
        if name.startswith("_") or name.startswith("test_") or name.endswith("_test.py"):
            continue
        candidates.append(path)
    return sorted(candidates)


EXAMPLE_SCRIPTS = discover_examples()


def _run_script(path: pathlib.Path, timeout: int = 120) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("SPX_API_URL", SPX_API_URL)
    env.setdefault("MPLBACKEND", "Agg")  # Ensure non-interactive plotting backend.
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=str(path.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


@unittest.skip("Temporarily disable example tests")
class TestExampleScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _server_healthy(SPX_API_URL, timeout=5):
            raise unittest.SkipTest(f"SPX server not healthy at {SPX_API_URL}")

    def test_example_runs_without_errors(self):
        for script_path in EXAMPLE_SCRIPTS:
            display_name = str(script_path.relative_to(ROOT))
            with self.subTest(script=display_name):
                proc = _run_script(script_path)
                if proc.returncode != 0:
                    output = (
                        f"Script {display_name} exited with {proc.returncode}\n"
                        f"=== STDOUT ===\n{proc.stdout}\n"
                        f"=== STDERR ===\n{proc.stderr}"
                    )
                    self.fail(output)

    def test_discovery_found_examples(self):
        self.assertGreater(
            len(EXAMPLE_SCRIPTS),
            0,
            f"No example scripts found under {EXAMPLES_DIR}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
