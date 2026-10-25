# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus thermal controller client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "temperature": {"address": 0, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "setpoint": {"address": 2, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "heating_power": {"address": 4, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "power_on": {"address": 6, "kind": "coil"},
    "ambient": {"address": 7, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "overload": {"address": 9, "decoder": "u16"},
    "overload_threshold": {"address": 10, "decoder": "modbus_float_be", "bit_order": "ABCD"},
    "overload_hyst": {"address": 12, "decoder": "modbus_float_be", "bit_order": "ABCD"},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusThermalControllerSUTExample.modbus_to_float(registers, "ABCD")


class ModbusThermalControllerSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the SUT Modbus thermal controller model."""

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

    def state(self) -> str:
        return "connected" if self._client and self._client.connected else "disconnected"

    # Read helpers ------------------------------------------------------
    def read_temperature(self) -> float:
        return self._read_float("temperature")

    def read_setpoint(self) -> float:
        return self._read_float("setpoint")

    def read_heating_power(self) -> float:
        return self._read_float("heating_power")

    def read_overload_flag(self) -> int:
        return int(self._read_field("overload"))

    def read_power_state(self) -> int:
        return int(self._read_coil_field("power_on"))

    # Write helpers -----------------------------------------------------
    def set_power_state(self, powered: bool) -> None:
        self._write_coil_field("power_on", powered)

    def set_setpoint(self, value: float) -> None:
        self._write_float_field("setpoint", value)

    def set_ambient(self, value: float) -> None:
        self._write_float_field("ambient", value)

    def set_overload_threshold(self, value: float) -> None:
        self._write_float_field("overload_threshold", value)

    def set_overload_hysteresis(self, value: float) -> None:
        self._write_float_field("overload_hyst", value)

    # Internal helpers --------------------------------------------------
    def _read_float(self, field: str) -> float:
        return float(self._read_field(field))

    def _read_field(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        if config.get("kind") == "coil":
            return float(self._read_coil_field(field_name))
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        return float(decoder.decode(registers))

    def _write_float_field(self, field: str, value: float) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        registers = self._float_to_registers(value)
        self._write_registers(address, registers)

    def _write_coil_field(self, field: str, value: bool) -> None:
        config = self._get_field_config(field)
        if config.get("kind", "coil") != "coil":
            raise ValueError(f"Field '{field}' is not configured as a coil")
        address = self._get_address(config, field)
        self._write_coils(address, bool(value))

    def _read_coil_field(self, field: str) -> int:
        config = self._get_field_config(field)
        if config.get("kind", "coil") != "coil":
            raise ValueError(f"Field '{field}' is not configured as a coil")
        address = self._get_address(config, field)
        bits = self._read_coils(address, count=1)
        if not bits:
            raise RuntimeError(f"Modbus coil read returned empty result at {address}")
        return int(bool(bits[0]))


__all__ = ["ModbusThermalControllerSUTExample", "ModbusTcpClient"]
