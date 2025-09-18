

import os
import sys
import time
import pathlib
import subprocess
import urllib.request
import urllib.error

import pytest

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


@pytest.fixture(scope="session", autouse=True)
def ensure_server():
    """Skip all tests if the SPX server is not reachable (useful for local runs)."""
    if not _server_healthy(SPX_API_URL, timeout=5):
        pytest.skip(f"SPX server not healthy at {SPX_API_URL}")


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
    for p in EXAMPLES_DIR.glob("**/*.py"):
        name = p.name.lower()
        if name in ("__init__.py",):
            continue
        if name.startswith("_") or name.startswith("test_") or name.endswith("_test.py"):
            continue
        candidates.append(p)
    return sorted(candidates)


EXAMPLE_SCRIPTS = discover_examples()


def _run_script(path: pathlib.Path, timeout: int = 120) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("SPX_API_URL", SPX_API_URL)
    # Ensure non-interactive plotting backend for CI/headless
    env.setdefault("MPLBACKEND", "Agg")
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=str(path.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


@pytest.mark.parametrize("script_path", EXAMPLE_SCRIPTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_example_runs_without_errors(script_path: pathlib.Path):
    proc = _run_script(script_path)
    if proc.returncode != 0:
        print("=== STDOUT ===\n" + proc.stdout)
        print("=== STDERR ===\n" + proc.stderr)
    assert proc.returncode == 0


def test_discovery_found_examples():
    assert len(EXAMPLE_SCRIPTS) > 0, f"No example scripts found under {EXAMPLES_DIR}"
