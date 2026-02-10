# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus Prevac XR40B-EC client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "status_word_1": {"address": 1, "decoder": "u16"},
    "emission_voltage_v": {"address": 5, "decoder": "u16"},
    "emission_current_ma": {
        "address": 6,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "k__emission_voltage_set_v": {"address": 41, "decoder": "u16"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusPrevacXR40BECExample.modbus_to_float(registers, "ABCD")


class ModbusPrevacXR40BECExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Prevac XR40B-EC Modbus model."""

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

    def set_u16(self, field: str, value: int) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        self._write_registers(address, [int(value) & 0xFFFF])

    def _read(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        return decoder.decode(registers)


__all__ = ["ModbusPrevacXR40BECExample", "ModbusTcpClient"]
