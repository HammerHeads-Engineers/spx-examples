# Software driver for the Modbus stepper motor model used in tests.
from __future__ import annotations

import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

try:  # pymodbus >= 3.0
    from pymodbus.client import ModbusTcpClient  # type: ignore
except Exception:  # pragma: no cover - fallback for < 3.0
    try:
        from pymodbus.client.sync import ModbusTcpClient  # type: ignore
    except Exception:  # pragma: no cover - pymodbus unavailable
        ModbusTcpClient = None  # type: ignore

try:
    from pymodbus.exceptions import ConnectionException, ModbusIOException  # type: ignore
except Exception:  # pragma: no cover - fallback when pymodbus unavailable
    class ModbusIOException(Exception):  # type: ignore
        pass

    class ConnectionException(ModbusIOException):  # type: ignore
        pass

RegisterConfig = Dict[str, Any]
ModbusMap = Dict[str, RegisterConfig]

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


@dataclass(frozen=True)
class RegisterDecoder:
    count: int
    fn: Callable[[Sequence[int]], Any]

    def decode(self, registers: Sequence[int]) -> Any:
        if len(registers) != self.count:
            raise ValueError(
                f"Decoder expected {self.count} registers, got {len(registers)}"
            )
        return self.fn(registers)


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_u32(registers: Sequence[int]) -> int:
    high, low = registers
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def _decode_u32_float_be(registers: Sequence[int]) -> float:
    high, low = registers
    return ModbusStepperDriver._registers_to_float(high, low)


def _decode_u32_from_two_u16_be(registers: Sequence[int]) -> float:
    return float(ModbusStepperDriver._u32_from_two_u16_be(registers))


class ModbusStepperDriver:
    """Thin wrapper around pymodbus for talking to the SPX Modbus stepper model."""

    _MIN_CLIENT_TIMEOUT = 0.05

    _DECODER_REGISTRY: Dict[str, RegisterDecoder] = {
        "u16": RegisterDecoder(count=1, fn=_decode_u16),
        "u32": RegisterDecoder(count=2, fn=_decode_u32),
        "u32_float_be": RegisterDecoder(count=2, fn=_decode_u32_float_be),
        "u32_from_two_u16_be": RegisterDecoder(
            count=2, fn=_decode_u32_from_two_u16_be
        ),
        "modbus_float_be": RegisterDecoder(
            count=2, fn=lambda regs: ModbusStepperDriver.modbus_to_float(regs, "ABCD")
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
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise RuntimeError(
                "pymodbus is not available. Install pymodbus to use ModbusStepperDriver."
            )
        client_kwargs = {"host": host, "port": port}
        if timeout is not None:
            client_timeout = (
                timeout
                if timeout and timeout > 0.0
                else self._MIN_CLIENT_TIMEOUT
            )
            # pymodbus rejects non-positive values; clamp to a minimal positive timeout.
            client_kwargs["timeout"] = client_timeout
        self._client = ModbusTcpClient(**client_kwargs)
        self.unit_id = unit_id
        self.retries = retries
        self.timeout = timeout

        self.mapping: ModbusMap = deepcopy(mapping) if mapping else deepcopy(
            DEFAULT_MODBUS_MAP
        )

    def connect(self) -> bool:
        return bool(self._client.connect())

    def close(self) -> None:
        self._client.close()

    # Write operations
    def set_enable(self, value: int) -> None:
        config = self._get_field_config("enable")
        address = self._get_address(config, "enable")
        self._ensure_connected()
        self._call_with_unit_kwarg("write_coil", address, bool(value))

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
        self._ensure_connected()
        registers = self._float_to_registers(value)
        self._call_with_unit_kwarg("write_registers", address, registers)

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

        ordered = ModbusStepperDriver._order_words(data, bit_order)
        packed_struct = struct.pack(">HH", ordered[0], ordered[1])
        value = struct.unpack(">f", packed_struct)[0]
        return round(value, 5)

    @staticmethod
    def _order_words(data: Sequence[int], bit_order: str) -> Sequence[int]:
        if len(data) != 2:
            raise ValueError(f"Expected 2 registers, got {len(data)}")
        order = bit_order.upper()
        if order == "ABCD":
            return data
        if len(order) != 4 or set(order) != {"A", "B", "C", "D"}:
            raise ValueError(f"Unsupported bit order '{bit_order}' for Modbus float decoding")
        byte_map = {
            "A": (data[0] >> 8) & 0xFF,
            "B": data[0] & 0xFF,
            "C": (data[1] >> 8) & 0xFF,
            "D": data[1] & 0xFF,
        }
        try:
            ordered_bytes = [byte_map[ch] for ch in order]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported bit order '{bit_order}' for Modbus float decoding"
            ) from exc
        word0 = (ordered_bytes[0] << 8) | ordered_bytes[1]
        word1 = (ordered_bytes[2] << 8) | ordered_bytes[3]
        return (word0, word1)

    def _call_with_unit_kwarg(self, method_name: str, *args, **kwargs):
        method = getattr(self._client, method_name)
        try:
            return method(*args, slave=self.unit_id, **kwargs)
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" in message and "'slave'" in message:
                return method(*args, unit=self.unit_id, **kwargs)
            raise

    def _get_field_config(self, field_name: str) -> RegisterConfig:
        try:
            return self.mapping[field_name]
        except KeyError as exc:
            raise ValueError(f"Field '{field_name}' not found in Modbus map") from exc

    def _get_address_for_field(self, field_name: str) -> int:
        config = self._get_field_config(field_name)
        return self._get_address(config, field_name)

    @staticmethod
    def _get_address(config: RegisterConfig, field_name: str) -> int:
        try:
            return int(config["address"])
        except KeyError as exc:
            raise ValueError(
                f"Missing 'address' for field '{field_name}' in Modbus map"
            ) from exc

    def _ensure_connected(self) -> None:
        if not self._client:
            raise RuntimeError("Modbus client not initialised")
        if not self._client.connected:  # type: ignore[attr-defined]
            connected = self._client.connect()
            if not connected:
                raise RuntimeError("Failed to connect Modbus client")

    def state(self) -> str:
        return "connected" if self._client and self._client.connected else "disconnected"
