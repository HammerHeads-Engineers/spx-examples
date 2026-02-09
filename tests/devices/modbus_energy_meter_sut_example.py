# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus energy meter client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ConnectionException,
    ModbusIOException,
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "voltage_l1_n_v": {"address": 50520, "decoder": "u32", "scale": 100.0},
    "voltage_l2_n_v": {"address": 50522, "decoder": "u32", "scale": 100.0},
    "voltage_l3_n_v": {"address": 50524, "decoder": "u32", "scale": 100.0},
    "current_l1_a": {"address": 50528, "decoder": "u32", "scale": 1000.0},
    "current_l2_a": {"address": 50530, "decoder": "u32", "scale": 1000.0},
    "current_l3_a": {"address": 50532, "decoder": "u32", "scale": 1000.0},
    "frequency_hz": {"address": 50526, "decoder": "u32", "scale": 100.0},
    "active_power_total_kw": {"address": 50536, "decoder": "u32", "scale": 10000.0},
    "power_factor": {"address": 50542, "decoder": "u32", "scale": 1000.0},
    "energy_import_kwh": {"address": 50780, "decoder": "u32", "scale": 1.0},
    "energy_export_kwh": {"address": 50786, "decoder": "u32", "scale": 1.0},
}


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusEnergyMeterSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Socomec DIRIS A-10 Modbus model."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u32": RegisterDecoder(count=2, fn=_decode_u32),
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 2.0,
        mapping: Optional[ModbusMap] = None,
    ) -> None:
        super().__init__(
            default_map=DEFAULT_MODBUS_MAP,
            mapping=mapping,
            host=host,
            port=port,
            unit_id=unit_id,
            timeout=timeout,
        )

    def read_voltage_l1_n(self) -> float:
        return self._read_scaled("voltage_l1_n_v")

    def read_current_l1(self) -> float:
        return self._read_scaled("current_l1_a")

    def read_frequency(self) -> float:
        return self._read_scaled("frequency_hz")

    def read_active_power_total_kw(self) -> float:
        return self._read_scaled("active_power_total_kw")

    def read_power_factor(self) -> float:
        return self._read_scaled("power_factor")

    def read_energy_import_kwh(self) -> float:
        return self._read_scaled("energy_import_kwh")

    def read_energy_export_kwh(self) -> float:
        return self._read_scaled("energy_export_kwh")

    def _read_scaled(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u32")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")

        registers = self._read_input_registers(address, decoder.count)
        raw_value = decoder.decode(registers)
        scale = config.get("scale", 1.0)
        if scale == 0:
            raise ValueError(f"Scale for field '{field_name}' must be non-zero")
        return float(raw_value) / float(scale)

    def _read_input_registers(self, address: int, count: int):
        attempts = 3
        delay = self.timeout if self.timeout and self.timeout > 0 else 0.1
        delay = min(delay, 0.5)
        last_error: Optional[BaseException] = None

        for attempt in range(attempts):
            try:
                self._ensure_connected()
                result = self._call_with_unit_kwarg(
                    "read_input_registers", address, count=count
                )
            except RuntimeError as exc:
                if "Failed to connect Modbus client" not in str(exc):
                    raise
                last_error = exc
            except (ConnectionException, ModbusIOException, OSError) as exc:
                last_error = exc
            else:
                if result is None:
                    last_error = RuntimeError(
                        f"Modbus read returned no response at address {address}"
                    )
                elif result.isError():  # pragma: no cover - delegated to pymodbus
                    last_error = RuntimeError(
                        f"Modbus read failed at address {address}"
                    )
                else:
                    return result.registers

            if self._client:
                self._client.close()

            if attempt < attempts - 1:
                import time

                time.sleep(delay)
                continue
            break

        error_message = (
            f"Modbus read failed at address {address} after {attempts} attempts"
        )
        if last_error is None:
            raise RuntimeError(error_message)
        raise RuntimeError(error_message) from last_error


__all__ = ["ModbusEnergyMeterSUTExample", "ModbusTcpClient"]
