"""Exercise the release runner with passing, skipped and failed child tests."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("body, expected", [
    ("def test_real_check(): assert 42 == 42\n", 0),
    ("import pytest\ndef test_missing_runtime(): pytest.skip('runtime missing')\n", 1),
    ("def test_child_assertion(): assert 42 == 1\n", 1),
    ("# no tests collected\n", 5),
], ids=["passed", "skipped", "failed", "empty"])
def test_required_child_results(tmp_path, body, expected):
    test_file = tmp_path / "test_release_child.py"
    test_file.write_text(body, encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "tools.required_pytest", "-q",
                             "--rootdir", str(tmp_path), "--confcutdir", str(tmp_path), str(test_file)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr
    if "pytest.skip" in body:
        assert "Required tests were skipped: 1" in result.stderr
    if "42 == 1" in body:
        assert "FAILED" in result.stdout
