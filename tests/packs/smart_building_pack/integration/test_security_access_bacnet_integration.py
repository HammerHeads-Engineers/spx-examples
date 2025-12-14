# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration test for the BACnet security/access controller example."""

import os
import unittest

from tests.common.spx_utils import (
    ensure_instance,
    ensure_model,
    load_model_definition,
    wait_for_condition,
    wait_seconds,
)
from tests.common.repo import repo_root
from tests.devices.bacnet_client import (
    BACPYPES_AVAILABLE,
    BacnetTestClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "generic"
    / "security_access_controller__bacnet.yaml"
)
MODEL_KEY = "tests__security_access_bacnet"
INSTANCE_KEY = "security_access_bacnet"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
BACNET_HOST = os.environ.get("BACNET_TEST_HOST", "127.0.0.1")
BACNET_PORT = 47818


@unittest.skipUnless(BACPYPES_AVAILABLE, "BACpypes is required for BACnet integration tests")
class TestSecurityAccessBacnetIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._spx = spx_python
        client = spx_python.init(address=SPX_API_URL, product_key=product_key)

        model_def = load_model_definition(MODEL_PATH)
        comm_list = model_def.setdefault("communication", [])
        if not comm_list:
            comm_list.append({"bacnet": {}})
        bacnet_cfg = comm_list[0].setdefault("bacnet", {})
        bacnet_cfg["host"] = "0.0.0.0"
        bacnet_cfg["port"] = BACNET_PORT

        model_changed = ensure_model(client, MODEL_KEY, model_def)
        cls._instance = ensure_instance(
            client,
            INSTANCE_KEY,
            MODEL_KEY,
            recreate=model_changed,
            ensure_running=True,
        )

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
            device_id=9200,
            remote_host=BACNET_HOST,
            remote_port=BACNET_PORT,
            bind_port=0,
        )
        self.client.start_core()
        wait_seconds(0.2)

        try:
            _ = self.client.read_bool(("binaryInput", 11), "presentValue")
        except TimeoutError as exc:
            self.client.stop_core()
            self.skipTest(
                f"BACnet server not reachable at {BACNET_HOST}:{BACNET_PORT}: {exc}"
            )
        except Exception:
            self.client.stop_core()
            raise

        # Baseline disarmed state.
        attrs = self.model["attributes"]
        attrs["entry_door_contact"].internal_value = 0
        attrs["server_room_contact"].internal_value = 0
        attrs["motion_zone"].internal_value = 0
        attrs["lock_command"].internal_value = 1
        attrs["siren_command"].internal_value = 0
        attrs["access_mode"].internal_value = 1
        wait_seconds(0.3)

    def tearDown(self):
        try:
            self.model["attributes"]["access_mode"].internal_value = 1
            self.model["attributes"]["siren_command"].internal_value = 0
        except Exception:
            pass
        try:
            self.client.stop_core()
        except Exception:
            pass

    def test_lock_control_roundtrip(self):
        attrs = self.model["attributes"]
        # Unlock via BACnet write.
        self.client.write_bool(("binaryOutput", 21), "presentValue", False, priority=8)
        self.assertTrue(
            wait_for_condition(
                lambda: int(attrs["lock_command"].internal_value or 0) == 0,
                timeout=3.0,
            ),
            "lock_command should reflect BACnet write",
        )

        lock_value = self.client.read_bool(("binaryOutput", 21), "presentValue")
        self.assertEqual(lock_value, 0)

    def test_alarm_on_motion_when_armed(self):
        attrs = self.model["attributes"]
        # Arm-away via BACnet, then simulate motion.
        self.client.write_unsigned(("multiStateValue", 30), "presentValue", 3, priority=8)
        self.assertTrue(
            wait_for_condition(
                lambda: int(attrs["access_mode"].internal_value or 0) in (3, 4),
                timeout=3.0,
            ),
            "access_mode should reflect armed-away state",
        )

        attrs["motion_zone"].internal_value = 1
        self.assertTrue(
            wait_for_condition(
                lambda: int(attrs["siren_command"].internal_value or 0) == 1,
                timeout=4.0,
            ),
            "siren_command should be asserted on motion while armed",
        )

        alarm_state = self.client.read_bool(("binaryValue", 40), "presentValue")
        self.assertEqual(alarm_state, 1)

        access_state = self.client.read_unsigned(("multiStateValue", 30), "presentValue")
        self.assertEqual(access_state, 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
