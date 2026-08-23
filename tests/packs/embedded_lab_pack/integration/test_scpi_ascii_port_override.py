# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import unittest
from pathlib import Path

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.repo import repo_root
from tests.common.spx_utils import (
    ensure_instance,
    ensure_model,
    load_model_definition,
    wait_for_condition,
)
from tests.devices.scpi_function_generator_sut_example import (
    ScpiFunctionGeneratorSUTExample,
)


ROOT = repo_root()
MODEL_ID = "Lab.FunctionGenerator.SiglentSdg1032X.Scpi"
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "lab"
    / "function_generator"
    / "siglent"
    / "siglent_sdg1032x__scpi.yaml"
)
INSTANCE_KEY = "spx_lab_function_generator"
CUSTOM_ASCII_PORT = 5026
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiAsciiPortOverride(unittest.TestCase):
    """Verify a generated instance honors a non-default ASCII port."""

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        if not (product_key := os.environ.get("SPX_PRODUCT_KEY")):
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._model = load_model_definition(Path(MODEL_PATH), model_key=MODEL_ID)
        ensure_model(cls._client, MODEL_ID, cls._model)
        cls._instance = ensure_instance(
            cls._client,
            INSTANCE_KEY,
            MODEL_ID,
            model_def=cls._model,
            meta_parameters={"ascii_port": CUSTOM_ASCII_PORT},
            recreate=True,
            ensure_running=False,
            reset_on_create=True,
            start_on_create=True,
        )

    @classmethod
    def tearDownClass(cls):
        # Keep the installer-created instance available for the shared
        # function generator suite; it resets and starts it when needed.
        if (instance := getattr(cls, "_instance", None)) is not None:
            try:
                instance.stop()
            except Exception:
                pass

    def test_explicit_ascii_port_is_active_and_serves_scpi(self) -> None:
        port = wait_for_ascii_port(self._instance, timeout=10.0, interval=0.2)
        self.assertEqual(port, CUSTOM_ASCII_PORT)

        sut = ScpiFunctionGeneratorSUTExample(port=port, timeout=1.0)
        try:
            connected = wait_for_condition(
                sut.connect,
                timeout=5.0,
                interval=0.2,
            )
            self.assertTrue(connected, f"SCPI server did not open port {port}")
            self.assertEqual(
                sut.query("*IDN?"),
                "SIGLENT,SDG1032X,SDG1X00000000,1.01",
            )
        finally:
            sut.close()
