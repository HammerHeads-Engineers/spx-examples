# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.thermal_controller_sut_example as shared_tc

from tests.common.spx_utils import require_existing_instance


SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_hvac_controller"
MODEL_ID = "Process.ThermalController.Modbus"


class TestThermalControllerSUTExampleIntegration(shared_tc.TestThermalControllerSUTExampleIntegration):
    """Run the shared thermal-controller suite against the installer-created instance."""

    @classmethod
    def setUpClass(cls):
        if shared_tc.ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise unittest.SkipTest(
                "pymodbus is not available. Install pymodbus to run Modbus integration tests."
            )

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._spx = spx_python
        cls._client = spx_python.init(address=SPX_API_URL, product_key=product_key)
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
