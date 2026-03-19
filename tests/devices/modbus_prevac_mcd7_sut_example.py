# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""SUT client for the Prevac MCD7 Modbus model used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import ModbusMap, ModbusSUTBase, ModbusTcpClient, RegisterDecoder

DEFAULT_MODBUS_MAP: ModbusMap = {
    # 0-based inclusive ranges, matching the model mapping.
    "measure_done": {"address": [0, 0], "decoder": "u16"},
    "measure_start": {"address": [1, 1], "decoder": "u16"},
    "measure_config": {"address": [2, 2], "decoder": "u16"},
    "dwell_time": {"address": [3, 3], "decoder": "u16"},
    "ch_1_impulse": {"address": [4, 5], "decoder": "u32"},
    "ch_2_impulse": {"address": [6, 7], "decoder": "u32"},
    "ch_3_impulse": {"address": [8, 9], "decoder": "u32"},
    "ch_4_impulse": {"address": [10, 11], "decoder": "u32"},
    "ch_5_impulse": {"address": [12, 13], "decoder": "u32"},
    "ch_6_impulse": {"address": [14, 15], "decoder": "u32"},
    "ch_7_impulse": {"address": [16, 17], "decoder": "u32"},
    "ch_1_comparator": {"address": [18, 18], "decoder": "u16"},
    "ch_2_comparator": {"address": [19, 19], "decoder": "u16"},
    "ch_3_comparator": {"address": [20, 20], "decoder": "u16"},
    "ch_4_comparator": {"address": [21, 21], "decoder": "u16"},
    "ch_5_comparator": {"address": [22, 22], "decoder": "u16"},
    "ch_6_comparator": {"address": [23, 23], "decoder": "u16"},
    "ch_7_comparator": {"address": [24, 24], "decoder": "u16"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusPrevacMCD7SUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the Prevac MCD7 detector model."""

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

    def read_u16(self, field_name: str) -> int:
        return int(self._read(field_name))

    def read_u32(self, field_name: str) -> int:
        return int(self._read(field_name))

    def read_impulses(self) -> Sequence[int]:
        return [self.read_u32(f"ch_{idx}_impulse") for idx in range(1, 8)]

    def set_u16(self, field_name: str, value: int) -> None:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        self._write_registers(address, [int(value) & 0xFFFF])

    def start_measurement(self, dwell_time_ms: int = 200) -> None:
        self.set_u16("dwell_time", dwell_time_ms)
        self.set_u16("measure_start", 1)

    def _read(self, field_name: str):
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        return decoder.decode(registers)


__all__ = [
    "ModbusPrevacMCD7SUTExample",
    "ModbusTcpClient",
]
