# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SUT implementation: Modbus EM24 energy meter client."""
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
    "voltage_l1_n_v": {"address": 0, "decoder": "u32", "scale": 10.0},
    "current_l1_a": {"address": 12, "decoder": "u32", "scale": 1000.0},
    "active_power_total_w": {"address": 40, "decoder": "u32", "scale": 10.0},
    "power_factor_total": {"address": 49, "decoder": "u16", "scale": 1000.0},
    "frequency_hz": {"address": 51, "decoder": "u16", "scale": 10.0},
    "energy_import_total_kwh": {"address": 52, "decoder": "u32", "scale": 10.0},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class ModbusEm24SUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the EM24 Modbus energy meter."""

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
        retries: int = 3,
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
        self.retries = retries

    def read_voltage_l1_n_v(self) -> float:
        return self._read_decoded_register("voltage_l1_n_v")

    def read_current_l1_a(self) -> float:
        return self._read_decoded_register("current_l1_a")

    def read_active_power_total_w(self) -> float:
        return self._read_decoded_register("active_power_total_w")

    def read_power_factor_total(self) -> float:
        return self._read_decoded_register("power_factor_total")

    def read_frequency_hz(self) -> float:
        return self._read_decoded_register("frequency_hz")

    def read_energy_import_total_kwh(self) -> float:
        return self._read_decoded_register("energy_import_total_kwh")

    def _read_decoded_register(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)

        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(
                f"Unsupported decoder '{decoder_key}' for field '{field_name}'"
            )

        registers = self._read_registers(address, decoder.count)
        raw_value = decoder.decode(registers)
        scale = config.get("scale", 1.0)
        if scale == 0:
            raise ValueError(f"Scale for field '{field_name}' must be non-zero")
        return float(raw_value) / scale

    def _read_registers(self, address: int, count: int):
        attempts = max(1, int(self.retries) + 1)
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


__all__ = ["ModbusEm24SUTExample", "ModbusTcpClient"]
