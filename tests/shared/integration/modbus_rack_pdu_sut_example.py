# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the APC Rack PDU Modbus model."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds
from tests.common.repo import repo_root
from tests.devices.modbus_rack_pdu_sut_example import (
    ModbusRackPduSUTExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "apc"
    / "rack_pdu_rpdu2g__modbus.yaml"
)
MODEL_KEY = "tests__apc_rack_pdu_2g"
INSTANCE_KEY = "apc_rack_pdu_2g"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


def _quantize(value: float, scale: float) -> float:
    return round(value * scale) / scale


class TestModbusRackPduSUTExampleIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
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
        (
            cls._client,
            cls._instance,
            cls._model_changed,
        ) = bootstrap_model_instance(
            spx_python,
            product_key=product_key,
            base_url=SPX_BASE_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.2)

        try:
            comm = self.model["communication"]["modbus_slave"]
            attach = getattr(comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass

        try:
            port, unit_id = wait_for_modbus_endpoint(
                self.model,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self.sut = ModbusRackPduSUTExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not self.sut.connect():
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def test_scaled_registers(self):
        attrs = self.model["attributes"]
        attrs["k__phase_l1_current_a"].internal_value = 8.0
        attrs["k__phase_l2_current_a"].internal_value = 7.5
        attrs["k__phase_l3_current_a"].internal_value = 7.0
        attrs["k__phase_l1_voltage_v"].internal_value = 230.0
        attrs["k__phase_l2_voltage_v"].internal_value = 229.0
        attrs["k__phase_l3_voltage_v"].internal_value = 231.0
        attrs["k__phase_l1_power_kw"].internal_value = 1.8
        attrs["k__phase_l2_power_kw"].internal_value = 1.7
        attrs["k__phase_l3_power_kw"].internal_value = 1.6
        attrs["k__phase_l1_apparent_power_kva"].internal_value = 1.95
        attrs["k__phase_l2_apparent_power_kva"].internal_value = 1.9
        attrs["k__phase_l3_apparent_power_kva"].internal_value = 1.85
        wait_seconds(0.4)

        l1_current = self.sut.read_scaled("phase_l1_current")
        l1_voltage = self.sut.read_scaled("phase_l1_voltage")
        l2_current = self.sut.read_scaled("phase_l2_current")
        l3_current = self.sut.read_scaled("phase_l3_current")
        device_power = self.sut.read_scaled("device_real_load_power")
        device_state = self.sut.read_scaled("device_state")

        self.assertAlmostEqual(l1_current, _quantize(8.0, 10.0))
        self.assertAlmostEqual(l1_voltage, _quantize(230.0, 1.0))
        self.assertAlmostEqual(l2_current, _quantize(7.5, 10.0))
        self.assertAlmostEqual(l3_current, _quantize(7.0, 10.0))

        expected_device_power = _quantize(1.8 + 1.7 + 1.6, 100.0)
        self.assertAlmostEqual(device_power, expected_device_power, places=2)
        self.assertEqual(int(device_state), 2)


__all__ = ["TestModbusRackPduSUTExampleIntegration", "ModbusTcpClient"]
