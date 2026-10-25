# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import time
import unittest
from typing import Optional, Sequence

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition

try:  # pymodbus >= 3.x
    from pymodbus.client import ModbusTcpClient  # type: ignore
except Exception:  # pragma: no cover - fallback for pymodbus < 3.x
    try:
        from pymodbus.client.sync import ModbusTcpClient  # type: ignore
    except Exception:  # pragma: no cover - pymodbus unavailable
        ModbusTcpClient = None  # type: ignore


MODEL_ID = "Energy.PowerMeter.AbbM1M.Modbus"
INSTANCE_KEY = "spx_abb_m1m_power_meter_modbus"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
READ_RETRY_TIMEOUT = float(os.environ.get("ABB_M1M_SMOKE_READ_TIMEOUT", "6.0"))


def _instance_state(instance) -> Optional[str]:
    try:
        state = instance.state
    except Exception:
        state = None
    if isinstance(state, str):
        return state

    try:
        doc = instance.get()
    except Exception:
        doc = None
    if isinstance(doc, dict):
        value = doc.get("state")
        if isinstance(value, str):
            return value
        attr = doc.get("attr")
        if isinstance(attr, dict):
            state_attr = attr.get("state")
            if isinstance(state_attr, dict):
                state_value = state_attr.get("value")
                if isinstance(state_value, str):
                    return state_value
    return None


def _float_attr(attribute) -> Optional[float]:
    try:
        value = attribute.internal_value
    except Exception:
        value = None
    if value is None:
        value = attribute
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_input_registers(client, address: int, count: int, unit_id: int):
    try:
        return client.read_input_registers(address=address, count=count, slave=unit_id)
    except TypeError:
        return client.read_input_registers(address=address, count=count, unit=unit_id)


def _decode_u32_be(registers: Sequence[int]) -> int:
    if len(registers) != 2:
        raise ValueError(f"Expected 2 registers, got {len(registers)}")
    return ((int(registers[0]) & 0xFFFF) << 16) | (int(registers[1]) & 0xFFFF)


def _read_u32_with_retry(client, address: int, unit_id: int, *, timeout: float) -> int:
    deadline = time.time() + max(0.1, timeout)
    last_error: Optional[BaseException] = None
    last_value: Optional[int] = None

    while time.time() < deadline:
        try:
            response = _read_input_registers(client, address=address, count=2, unit_id=unit_id)
            if response is None:
                raise RuntimeError(f"No Modbus response at address {address}")
            if response.isError():  # pragma: no cover - delegated to pymodbus
                raise RuntimeError(f"Modbus error at address {address}: {response}")

            value = _decode_u32_be(response.registers)
            last_value = value
            if value > 0:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)

    if last_error is not None:
        raise AssertionError(
            f"Unable to read positive u32 from address {address} within {timeout}s: {last_error}"
        ) from last_error
    raise AssertionError(
        f"Unable to read positive u32 from address {address} within {timeout}s; last_value={last_value!r}"
    )


class TestModbusAbbM1MSmokeIntegration(unittest.TestCase):
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

    @classmethod
    def _debug_snapshot(cls) -> str:
        state = _instance_state(cls._instance)
        try:
            port, unit_id = wait_for_modbus_endpoint(
                cls._instance,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=1.0,
                interval=0.1,
            )
            endpoint = f"{port}/{unit_id}"
        except Exception as exc:
            endpoint = f"unresolved ({exc})"

        attrs = cls._instance["attributes"]
        voltage = _float_attr(attrs["voltage_system_v"])
        power = _float_attr(attrs["active_power_total_kw"])
        frequency = _float_attr(attrs["frequency_hz"])
        return (
            f"state={state!r}, endpoint={endpoint}, "
            f"voltage_system_v={voltage!r}, active_power_total_kw={power!r}, frequency_hz={frequency!r}"
        )

    def test_instance_starts_and_endpoint_resolves(self):
        is_running = wait_for_condition(
            lambda: (_instance_state(self._instance) or "").lower() == "running",
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(is_running, f"ABB M1M instance did not reach RUNNING ({self._debug_snapshot()})")

        port, unit_id = wait_for_modbus_endpoint(
            self._instance,
            comm_keys=("modbus_slave", "modbus_tcp"),
            timeout=10.0,
            interval=0.2,
        )
        self.assertGreater(port, 0, f"Invalid Modbus port resolved ({self._debug_snapshot()})")
        self.assertGreater(unit_id, 0, f"Invalid Modbus unit id resolved ({self._debug_snapshot()})")

    def test_modbus_key_registers_match_runtime_attributes(self):
        port, unit_id = wait_for_modbus_endpoint(
            self._instance,
            comm_keys=("modbus_slave", "modbus_tcp"),
            timeout=10.0,
            interval=0.2,
        )

        client = ModbusTcpClient(host="127.0.0.1", port=port, timeout=1.0)
        if not wait_for_condition(lambda: bool(client.connect()), timeout=5.0, interval=0.2):
            self.fail(f"Modbus endpoint is unreachable at 127.0.0.1:{port} (unit {unit_id})")

        try:
            voltage_raw = _read_u32_with_retry(
                client,
                address=23296,
                unit_id=unit_id,
                timeout=READ_RETRY_TIMEOUT,
            )
            active_power_raw = _read_u32_with_retry(
                client,
                address=23322,
                unit_id=unit_id,
                timeout=READ_RETRY_TIMEOUT,
            )
            frequency_raw = _read_u32_with_retry(
                client,
                address=23346,
                unit_id=unit_id,
                timeout=READ_RETRY_TIMEOUT,
            )
        finally:
            client.close()

        attrs = self._instance["attributes"]
        voltage_system_v = _float_attr(attrs["voltage_system_v"])
        active_power_total_kw = _float_attr(attrs["active_power_total_kw"])
        frequency_hz = _float_attr(attrs["frequency_hz"])

        self.assertIsNotNone(voltage_system_v, "Unable to read attribute 'voltage_system_v'")
        self.assertIsNotNone(active_power_total_kw, "Unable to read attribute 'active_power_total_kw'")
        self.assertIsNotNone(frequency_hz, "Unable to read attribute 'frequency_hz'")

        voltage_from_modbus = voltage_raw / 10.0
        active_power_from_modbus = active_power_raw / 100000.0
        frequency_from_modbus = frequency_raw / 100.0

        self.assertAlmostEqual(
            voltage_from_modbus,
            float(voltage_system_v),
            delta=2.0,
            msg=f"Voltage mismatch ({self._debug_snapshot()})",
        )
        self.assertAlmostEqual(
            active_power_from_modbus,
            float(active_power_total_kw),
            delta=0.5,
            msg=f"Active power mismatch ({self._debug_snapshot()})",
        )
        self.assertAlmostEqual(
            frequency_from_modbus,
            float(frequency_hz),
            delta=0.2,
            msg=f"Frequency mismatch ({self._debug_snapshot()})",
        )
