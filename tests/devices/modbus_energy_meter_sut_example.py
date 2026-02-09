# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus energy meter client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "frequency": {"address": 264, "decoder": "float_be", "scale": 1.0},
    "voltage_l1_n": {"address": 284, "decoder": "float_be", "scale": 1.0},
    "voltage_l2_n": {"address": 286, "decoder": "float_be", "scale": 1.0},
    "voltage_l3_n": {"address": 288, "decoder": "float_be", "scale": 1.0},
    "voltage_l1_l2": {"address": 300, "decoder": "float_be", "scale": 1.0},
    "voltage_l2_l3": {"address": 302, "decoder": "float_be", "scale": 1.0},
    "voltage_l3_l1": {"address": 304, "decoder": "float_be", "scale": 1.0},
    "current_l1": {"address": 308, "decoder": "float_be", "scale": 1.0},
    "current_l2": {"address": 310, "decoder": "float_be", "scale": 1.0},
    "current_l3": {"address": 312, "decoder": "float_be", "scale": 1.0},
    "active_power_l1": {"address": 344, "decoder": "float_be", "scale": 1.0},
    "active_power_l2": {"address": 346, "decoder": "float_be", "scale": 1.0},
    "active_power_l3": {"address": 348, "decoder": "float_be", "scale": 1.0},
    "energy_import_total": {"address": 19843, "decoder": "u32", "scale": 1.0},
    "energy_export_total": {"address": 19846, "decoder": "u32", "scale": 1.0},
}


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusEnergyMeterSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Socomec DIRIS A-40 Modbus model."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u32": RegisterDecoder(count=2, fn=_decode_u32),
        "float_be": RegisterDecoder(
            count=2, fn=lambda regs: ModbusSUTBase.modbus_to_float(regs, "ABCD")
        ),
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
        return self._read_input_decoded("voltage_l1_n")

    def read_voltage_l1_l2(self) -> float:
        return self._read_input_decoded("voltage_l1_l2")

    def read_voltage_l2_n(self) -> float:
        return self._read_input_decoded("voltage_l2_n")

    def read_voltage_l3_n(self) -> float:
        return self._read_input_decoded("voltage_l3_n")

    def read_voltage_l2_l3(self) -> float:
        return self._read_input_decoded("voltage_l2_l3")

    def read_voltage_l3_l1(self) -> float:
        return self._read_input_decoded("voltage_l3_l1")

    def read_frequency(self) -> float:
        return self._read_input_decoded("frequency")

    def read_current_l1(self) -> float:
        return self._read_input_decoded("current_l1")

    def read_current_l2(self) -> float:
        return self._read_input_decoded("current_l2")

    def read_current_l3(self) -> float:
        return self._read_input_decoded("current_l3")

    def read_active_power_l1(self) -> float:
        return self._read_input_decoded("active_power_l1")

    def read_active_power_l2(self) -> float:
        return self._read_input_decoded("active_power_l2")

    def read_active_power_l3(self) -> float:
        return self._read_input_decoded("active_power_l3")

    def read_energy_import_total(self) -> float:
        return self._read_input_decoded("energy_import_total")

    def read_energy_export_total(self) -> float:
        return self._read_input_decoded("energy_export_total")

    def _read_input_decoded(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)

        decoder_key = config.get("decoder", "u32")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(
                f"Unsupported decoder '{decoder_key}' for field '{field_name}'"
            )

        registers = self._read_input_registers(address, decoder.count)
        raw_value = decoder.decode(registers)
        scale = config.get("scale", 1.0)
        if scale == 0:
            raise ValueError(f"Scale for field '{field_name}' must be non-zero")
        return float(raw_value) / scale

    def _read_input_registers(self, address: int, count: int):
        self._ensure_connected()
        result = self._call_with_unit_kwarg("read_input_registers", address, count=count)
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at address {address}")
        return result.registers


__all__ = ["ModbusEnergyMeterSUTExample", "ModbusTcpClient"]
