# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus APC Rack PDU client used in integration tests."""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .modbus_sut_base import (
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "device_power_rating": {"address": 40165, "decoder": "u16", "scale": 0.1},
    "device_current_rating": {"address": 40166, "decoder": "u16", "scale": 1.0},
    "device_real_load_power": {"address": 40208, "decoder": "u16", "scale": 0.01},
    "device_apparent_load_power": {"address": 40209, "decoder": "u16", "scale": 0.01},
    "device_power_factor": {"address": 40210, "decoder": "u16", "scale": 0.01},
    "device_energy": {"address": 40211, "decoder": "u32", "scale": 0.1},
    "device_state": {"address": 40213, "decoder": "u16", "scale": 1.0},
    "device_peak_power": {"address": 40214, "decoder": "u16", "scale": 0.01},
    "phase_l1_current": {"address": 40668, "decoder": "u16", "scale": 0.1},
    "phase_l1_voltage": {"address": 40669, "decoder": "u16", "scale": 1.0},
    "phase_l1_power": {"address": 40670, "decoder": "u16", "scale": 0.01},
    "phase_l1_apparent_power": {"address": 40671, "decoder": "u16", "scale": 0.01},
    "phase_l1_power_factor": {"address": 40672, "decoder": "u16", "scale": 0.01},
    "phase_l2_current": {"address": 40690, "decoder": "u16", "scale": 0.1},
    "phase_l2_voltage": {"address": 40691, "decoder": "u16", "scale": 1.0},
    "phase_l2_power": {"address": 40692, "decoder": "u16", "scale": 0.01},
    "phase_l2_apparent_power": {"address": 40693, "decoder": "u16", "scale": 0.01},
    "phase_l2_power_factor": {"address": 40694, "decoder": "u16", "scale": 0.01},
    "phase_l3_current": {"address": 40712, "decoder": "u16", "scale": 0.1},
    "phase_l3_voltage": {"address": 40713, "decoder": "u16", "scale": 1.0},
    "phase_l3_power": {"address": 40714, "decoder": "u16", "scale": 0.01},
    "phase_l3_apparent_power": {"address": 40715, "decoder": "u16", "scale": 0.01},
    "phase_l3_power_factor": {"address": 40716, "decoder": "u16", "scale": 0.01},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusRackPduSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the APC Rack PDU model."""

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

    def read_scaled(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")
        registers = self._read_holding_registers(address, decoder.count)
        value = float(decoder.decode(registers))
        scale = float(config.get("scale", 1.0))
        return value * scale


__all__ = ["ModbusRackPduSUTExample", "ModbusTcpClient"]
