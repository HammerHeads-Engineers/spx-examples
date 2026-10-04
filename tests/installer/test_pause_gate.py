"""The required catalog gate must reject missing licenses and child failures."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_required_pause_gate_fails_without_license():
    environment = dict(os.environ)
    environment.pop("SPX_PRODUCT_KEY", None)
    environment["SPX_PAUSE_QUALIFICATION"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "tools.required_pytest", "-q", "--tb=short",
         "tests/core/runtime/test_catalog_pause.py"],
        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode != 0
    assert "SPX_PRODUCT_KEY is required" in result.stdout
    assert "1 error" in result.stdout


def test_model_failures_are_aggregated_and_fail_the_whole_catalog():
    spec = importlib.util.spec_from_file_location("pause_catalog_gate", ROOT / "tests/core/runtime/test_catalog_pause.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    attempted, cleaned = [], []

    def call(method, path, data=None):
        if method == "PUT":
            attempted.append(next(iter(data.values()))["type"])
            raise RuntimeError("deliberate model failure")
        assert method == "DELETE"
        cleaned.append(path)

    properties = {}
    models = [{"id": name} for name in ("QA.First", "QA.Second")]
    with pytest.raises(AssertionError) as error:
        module.test_every_selected_model_freezes_and_resumes((call, models), properties.__setitem__)
    assert attempted == ["QA.First", "QA.Second"]
    assert len(cleaned) == 2
    assert "QA.First: deliberate model failure" in str(error.value)
    assert "QA.Second: deliberate model failure" in str(error.value)
    assert properties["selected_models"] == 2
