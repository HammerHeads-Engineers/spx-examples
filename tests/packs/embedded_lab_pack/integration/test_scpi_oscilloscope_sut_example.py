# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.scpi_oscilloscope_sut_example as shared_scpi

from tests.common.spx_utils import require_existing_instance


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_rigol_ds1000z_oscilloscope"
MODEL_ID = "Lab.Oscilloscope.RigolDs1000z.Scpi"


class TestScpiOscilloscopeSUTExample(shared_scpi.TestScpiOscilloscopeSUTExample):
    """Run the shared SCPI oscilloscope suite against the installer-created instance."""

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
