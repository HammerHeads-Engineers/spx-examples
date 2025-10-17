"""Example SUT implementation: Modbus stepper motor client used in integration tests."""
from __future__ import annotations

import time
from typing import Dict, Optional, Sequence, Tuple

from .modbus_sut_base import (
    ConnectionException,
    ModbusIOException,
    ModbusMap,
    ModbusSUTBase,
    ModbusTcpClient,
    RegisterDecoder,
)

DEFAULT_MODBUS_MAP: ModbusMap = {
    "enable": {"address": 0, "kind": "coil"},
    "position_command": {"address": 3},
    "position_feedback": {
        "address": 5,
        "decoder": "modbus_float_be",
        "scale": 1.0,
        "bit_order": "ABCD",
    },
    "velocity_command": {"address": 7},
    "velocity_feedback": {
        "address": 9,
        "decoder": "modbus_float_be",
        "scale": 1.0,
        "bit_order": "ABCD",
    },
    "max_speed": {"address": 19},
    "max_accel": {"address": 21},
    "max_decel": {"address": 23},
    "motion_error": {
        "address": 25,
        "decoder": "modbus_float_be",
        "scale": 1.0,
        "bit_order": "ABCD",
    },
    "velocity_goal": {"address": 27},
    "soft_limit_pos": {"address": 15},
    "soft_limit_neg": {"address": 17},
}


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def _decode_u32_float_be(registers: Sequence[int]) -> float:
    high, low = registers
    return ModbusStepperSUTExample._registers_to_float(high, low)


def _decode_u32_from_two_u16_be(registers: Sequence[int]) -> float:
    return float(ModbusStepperSUTExample._u32_from_two_u16_be(registers))


class ModbusStepperSUTExample(ModbusSUTBase):
    """Thin wrapper around pymodbus representing the SUT Modbus stepper model."""

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u16": RegisterDecoder(count=1, fn=_decode_u16),
        "u32": RegisterDecoder(count=2, fn=_decode_u32),
        "u32_float_be": RegisterDecoder(count=2, fn=_decode_u32_float_be),
        "u32_from_two_u16_be": RegisterDecoder(
            count=2, fn=_decode_u32_from_two_u16_be
        ),
        "modbus_float_be": RegisterDecoder(
            count=2, fn=lambda regs: ModbusStepperSUTExample.modbus_to_float(regs, "ABCD")
        ),
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

    # Write operations
    def set_enable(self, value: int) -> None:
        config = self._get_field_config("enable")
        address = self._get_address(config, "enable")
        self._write_coils(address, bool(value))

    def set_position_command(self, value: float) -> None:
        self._write_float(self._get_address_for_field("position_command"), value)

    def set_motion_limits(
        self,
        max_speed: Optional[float] = None,
        max_accel: Optional[float] = None,
        max_decel: Optional[float] = None,
    ) -> None:
        if max_speed is not None:
            self._write_float(self._get_address_for_field("max_speed"), max_speed)
        if max_accel is not None:
            self._write_float(self._get_address_for_field("max_accel"), max_accel)
        if max_decel is not None:
            self._write_float(self._get_address_for_field("max_decel"), max_decel)

    # Read helpers
    def read_position_feedback(self) -> float:
        return self._read_decoded_register("position_feedback")

    def read_velocity_feedback(self) -> float:
        return self._read_decoded_register("velocity_feedback")

    def read_motion_error(self) -> float:
        return self._read_decoded_register("motion_error")

    def _write_float(self, address: int, value: float) -> None:
        registers = self._float_to_registers(value)
        self._write_registers(address, registers)

    def _read_decoded_register(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)

        decoder_key = config.get("decoder", "u32_from_two_u16_be")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(
                f"Unsupported decoder '{decoder_key}' for field '{field_name}'"
            )

        registers = self._read_registers(address, decoder.count)
        if decoder_key == "modbus_float_be":
            bit_order = config.get("bit_order", "ABCD")
            raw_value = self.modbus_to_float(registers, bit_order)
        else:
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
                    "read_holding_registers", address, count=count
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
                time.sleep(delay)
                continue
            break

        error_message = (
            f"Modbus read failed at address {address} after {attempts} attempts"
        )
        if last_error is None:
            raise RuntimeError(error_message)
        raise RuntimeError(error_message) from last_error

    @staticmethod
    def _float_to_registers(value: float) -> Tuple[int, int]:
        import struct

        packed = struct.pack(">f", value)  # big-endian IEEE-754
        high, low = struct.unpack(">HH", packed)
        return high, low

    @staticmethod
    def _registers_to_float(high: int, low: int) -> float:
        import struct

        packed = struct.pack(">HH", high, low)
        return struct.unpack(">f", packed)[0]

    @staticmethod
    def _u32_from_two_u16_be(registers: Sequence[int]) -> int:
        if len(registers) != 2:
            raise ValueError(f"Expected 2 registers, got {len(registers)}")
        high, low = registers
        return ((high & 0xFFFF) << 16) | (low & 0xFFFF)

    @staticmethod
    def modbus_to_float(data: Sequence[int], bit_order: str) -> float:
        import struct

        ordered = ModbusStepperSUTExample._order_words(data, bit_order)
        packed_struct = struct.pack(">HH", ordered[0], ordered[1])
        value = struct.unpack(">f", packed_struct)[0]
        return round(value, 5)

    def _get_address_for_field(self, field_name: str) -> int:
        config = self._get_field_config(field_name)
        return self._get_address(config, field_name)

    def state(self) -> str:
        return "connected" if self._client and self._client.connected else "disconnected"


__all__ = ["ModbusStepperSUTExample", "ModbusTcpClient"]
