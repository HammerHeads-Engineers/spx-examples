# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.scpi_keysight_1000x_sut_example as shared_scpi

from tests.common.spx_utils import require_existing_instance


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_lab_oscilloscope"
MODEL_ID = "Lab.Oscilloscope.Keysight1000X.Scpi"


class TestScpiKeysight1000XOscilloscopeSUTExample(
    shared_scpi.TestScpiKeysight1000XOscilloscopeSUTExample
):
    """Run the shared Keysight SCPI oscilloscope suite against installer instance."""

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run SCPI integration tests.")

        cls._spx = spx_python
        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
            ensure_running=False,
        )
        cls._model_changed = False

        try:
            cls._instance.stop()
        except Exception:
            pass
        try:
            cls._instance.reset()
        except Exception:
            pass
        try:
            cls._instance.start()
        except Exception:
            pass
