# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration test for the BACnet fire alarm panel example."""

import os
import unittest

from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.bacnet_client import (
    BACPYPES_AVAILABLE,
    BacnetTestClient,
)


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_fire_alarm_panel_bacnet"
MODEL_ID = "Building.FireAlarmPanel.Bacnet"
BACNET_HOST = os.environ.get("BACNET_TEST_HOST", "127.0.0.1")
BACNET_PORT = 47828


@unittest.skipUnless(BACPYPES_AVAILABLE, "BACpypes is required for BACnet integration tests")
class TestFireAlarmBacnetIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
            ensure_running=False,
        )

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

    def setUp(self):
        self.model = self.__class__._instance

        # Ensure instance is running before attempting BACnet IO.
        def _state():
            try:
                return str(self.model.state).lower()
            except Exception:
                return None

        if _state() != "running":
            try:
                self.model.start()
            except Exception:
                pass
            wait_for_condition(lambda: _state() == "running", timeout=5.0)

        self.client = BacnetTestClient(
            device_id=9100,
            remote_host=BACNET_HOST,
            remote_port=BACNET_PORT,
            bind_port=0,
        )
        self.client.start_core()
        wait_seconds(0.2)

        # Probe connection; skip if BACnet server not reachable.
        try:
            _ = self.client.read_real(("analogInput", 1), "presentValue")
        except TimeoutError as exc:
            self.client.stop_core()
            self.skipTest(
                f"BACnet server not reachable at {BACNET_HOST}:{BACNET_PORT}: {exc}"
            )
        except Exception:
            self.client.stop_core()
            raise

    def tearDown(self):
        try:
            attrs = self.model["attributes"]
            attrs["manual_callpoint"].internal_value = 0
            attrs["siren_command"].internal_value = 0
        except Exception:
            pass
        try:
            self.client.stop_core()
        except Exception:
            pass

    def test_siren_write_and_status_readback(self):
        attrs = self.model["attributes"]
        attrs["siren_command"].internal_value = 0
        attrs["manual_callpoint"].internal_value = 0
        wait_seconds(0.3)

        # Read an input property via BACnet to confirm read path.
        smoke_value = self.client.read_real(("analogInput", 1), "presentValue")
        self.assertIsInstance(smoke_value, float)

        # Write siren on and ensure attribute follows.
        self.client.write_bool(("binaryOutput", 40), "presentValue", True, priority=8)
        self.assertTrue(
            wait_for_condition(
                lambda: int(attrs["siren_command"].internal_value or 0) == 1,
                timeout=3.0,
            ),
            "siren_command should reflect BACnet write",
        )

        siren_value = self.client.read_bool(("binaryOutput", 40), "presentValue")
        self.assertEqual(siren_value, 1)

        # Trigger manual call point and ensure system status moves to alarm (state 3).
        attrs["manual_callpoint"].internal_value = 1
        self.assertTrue(
            wait_for_condition(
                lambda: int(attrs["system_status"].internal_value or 0) == 3,
                timeout=3.0,
            ),
            "system_status should switch to alarm when manual call point is active",
        )
        status = self.client.read_unsigned(("multiStateValue", 50), "presentValue")
        self.assertEqual(status, 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
