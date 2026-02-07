# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus Prevac M600DC-PS client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "device_state": {"address": 0, "decoder": "u16"},
    "magnetron_power_w": {"address": 4, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "magnetron_voltage_v": {"address": 6, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "magnetron_current_ma": {"address": 8, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "power_set_w": {"address": 19, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "voltage_set_v": {"address": 21, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "current_set_ma": {"address": 23, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "flow_set_sccm": {"address": 25, "decoder": "modbus_float_be", "bit_order": "ABCD"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusPrevacM600DCPSExample.modbus_to_float(registers, "ABCD")


class ModbusPrevacM600DCPSExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Prevac M600DC-PS Modbus model."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u16": RegisterDecoder(count=1, fn=_decode_u16),
        "modbus_float_be": RegisterDecoder(count=2, fn=_decode_float_abcd),
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

    def read_u16(self, field: str) -> int:
        return int(self._read(field))

    def read_float(self, field: str) -> float:
        return float(self._read(field))

    def set_float(self, field: str, value: float) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        registers = self._float_to_registers(value)
        self._write_registers(address, registers)

    def _read(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        return decoder.decode(registers)


__all__ = ["ModbusPrevacM600DCPSExample", "ModbusTcpClient"]
