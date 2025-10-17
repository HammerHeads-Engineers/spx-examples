"""Example SUT implementation: Modbus vacuum gauge client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "rough_pressure": {"address": 0, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "high_pressure": {"address": 2, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "ionizer_enabled": {"address": 4, "kind": "coil"},
    "ionizer_available": {"address": 5, "decoder": "u16"},
    "ionizer_interlock": {"address": 6, "decoder": "u16"},
    "leak_event": {"address": 7, "kind": "coil"},
    "pumpdown_target": {"address": 8, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "upset_target": {"address": 10, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "discharge_event": {"address": 27, "kind": "coil"},
    "discharge_pressure": {"address": 28, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "discharge_decay": {"address": 30, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_setpoint_1": {"address": 12, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_setpoint_2": {"address": 14, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_setpoint_3": {"address": 16, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_setpoint_4": {"address": 18, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_setpoint_5": {"address": 20, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "relay_output_1": {"address": 22, "decoder": "u16"},
    "relay_output_2": {"address": 23, "decoder": "u16"},
    "relay_output_3": {"address": 24, "decoder": "u16"},
    "relay_output_4": {"address": 25, "decoder": "u16"},
    "relay_output_5": {"address": 26, "decoder": "u16"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusVacuumGaugeSUTExample.modbus_to_float(registers, "ABCD")


class ModbusVacuumGaugeSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the SUT Modbus vacuum gauge model."""

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

    def read_pressure(self, field: str) -> float:
        return float(self._read(field))

    def read_rough_pressure(self) -> float:
        return self.read_pressure("rough_pressure")

    def read_high_pressure(self) -> float:
        return self.read_pressure("high_pressure")

    def read_flag(self, field: str) -> int:
        return int(self._read(field))

    def set_coil(self, field: str, value: int) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        self._write_coils(address, bool(value))

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


__all__ = ["ModbusVacuumGaugeSUTExample", "ModbusTcpClient"]
