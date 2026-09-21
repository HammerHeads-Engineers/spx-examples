# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus EVSE client used in integration tests."""
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
    "pause_state": {"address": 41630, "decoder": "u16", "scale": 1.0},
    "max_charging_current_a": {"address": 41634, "decoder": "u16", "scale": 1.0},
    "current_l1_a": {"address": 41648, "decoder": "u16", "scale": 1.0},
    "voltage_l1_v": {"address": 41652, "decoder": "u16", "scale": 1.0},
    "active_power_sum_w": {"address": 41666, "decoder": "u16", "scale": 10.0},
    "power_factor_sum": {"address": 41670, "decoder": "u16", "scale": 100.0},
    "apparent_power_sum_va": {"address": 41674, "decoder": "u16", "scale": 1.0},
    "reactive_power_sum_var": {"address": 41678, "decoder": "u16", "scale": 1.0},
    "energy_consumed_kwh": {"address": 41693, "decoder": "u32", "scale": 10000.0},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return int(registers[0] & 0xFFFF)


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusVersiChargeAcSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Siemens VersiCharge AC model."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u16": RegisterDecoder(count=1, fn=_decode_u16),
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

    def read_max_charging_current(self) -> float:
        return self._read_scaled("max_charging_current_a")

    def read_current_l1(self) -> float:
        return self._read_scaled("current_l1_a")

    def read_voltage_l1(self) -> float:
        return self._read_scaled("voltage_l1_v")

    def read_active_power_sum(self) -> float:
        return self._read_scaled("active_power_sum_w")

    def read_power_factor_sum(self) -> float:
        return self._read_scaled("power_factor_sum")

    def read_energy_consumed_kwh(self) -> float:
        return self._read_scaled("energy_consumed_kwh")

    def write_max_charging_current(self, value_a: int) -> None:
        config = self._get_field_config("max_charging_current_a")
        address = self._get_address(config, "max_charging_current_a")
        self._write_registers(address, [int(value_a) & 0xFFFF])

    def _read_scaled(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")

        registers = self._read_holding_registers(address, decoder.count)
        raw_value = decoder.decode(registers)
        scale = config.get("scale", 1.0)
        if scale == 0:
            raise ValueError(f"Scale for field '{field_name}' must be non-zero")
        return float(raw_value) / float(scale)


__all__ = ["ModbusVersiChargeAcSUTExample", "ModbusTcpClient"]
