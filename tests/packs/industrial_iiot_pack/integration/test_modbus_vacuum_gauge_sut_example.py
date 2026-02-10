# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.modbus_vacuum_gauge_sut_example as shared_vg

from tests.common.spx_utils import require_existing_instance


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_vacuum_gauge"
MODEL_ID = "Process.VacuumGauge.Modbus"


class TestModbusVacuumGaugeSUTExampleIntegration(shared_vg.TestModbusVacuumGaugeSUTExampleIntegration):
    """Run the shared vacuum-gauge suite against the installer-created instance."""

    @classmethod
    def setUpClass(cls):
        if shared_vg.ModbusTcpClient is None:  # pragma: no cover - dependency missing
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
        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
            ensure_running=True,
        )
        cls._model_changed = False
