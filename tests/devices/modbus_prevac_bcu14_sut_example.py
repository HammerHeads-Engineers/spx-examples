# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus Prevac BCU14 client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "zone1_actual_temp_c": {"address": 12, "decoder": "u16"},
    "zone1_target_temp_c": {"address": 14, "decoder": "u16"},
    "zone2_actual_temp_c": {"address": 39, "decoder": "u16"},
    "zone2_target_temp_c": {"address": 41, "decoder": "u16"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


class ModbusPrevacBCU14SUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the BCU14 Modbus bakeout controller."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u16": RegisterDecoder(count=1, fn=_decode_u16),
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

    def _read(self, field_name: str) -> int:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        return int(decoder.decode(registers))

    def read_u16(self, field_name: str) -> int:
        return self._read(field_name)

    def write_u16(self, field_name: str, value: int) -> None:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        self._write_registers(address, [int(value) & 0xFFFF])

    def read_zone1_actual_temp(self) -> int:
        return self.read_u16("zone1_actual_temp_c")

    def read_zone1_target_temp(self) -> int:
        return self.read_u16("zone1_target_temp_c")

    def read_zone2_actual_temp(self) -> int:
        return self.read_u16("zone2_actual_temp_c")

    def read_zone2_target_temp(self) -> int:
        return self.read_u16("zone2_target_temp_c")

    def set_zone1_target_temp(self, value: int) -> None:
        self.write_u16("zone1_target_temp_c", value)

    def set_zone2_target_temp(self, value: int) -> None:
        self.write_u16("zone2_target_temp_c", value)


__all__ = ["ModbusPrevacBCU14SUTExample", "ModbusTcpClient"]
