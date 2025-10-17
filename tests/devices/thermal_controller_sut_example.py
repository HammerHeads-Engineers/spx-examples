"""Example SUT implementation: Modbus thermal controller client used in integration tests."""
from __future__ import annotations

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


RegisterConfig = Dict[str, Any]
ModbusMap = Dict[str, RegisterConfig]

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


@dataclass(frozen=True)
class RegisterDecoder:
    count: int
    fn: Callable[[Sequence[int]], Any]

    def decode(self, registers: Sequence[int]) -> Any:
        if len(registers) != self.count:
            raise ValueError(f"Decoder expected {self.count} registers, got {len(registers)}")
        return self.fn(registers)


def _decode_u16(registers: Sequence[int]) -> int:
    return registers[0] & 0xFFFF


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusThermalControllerSUTExample.modbus_to_float(registers, "ABCD")


class ModbusThermalControllerSUTExample:
    """Thin wrapper around pymodbus representing the SUT Modbus thermal controller model."""

    _MIN_CLIENT_TIMEOUT = 0.05

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
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise RuntimeError(
                "pymodbus is not available. Install pymodbus to use ModbusThermalControllerSUTExample."
            )
        client_kwargs = {"host": host, "port": port}
        if timeout is not None:
            client_timeout = timeout if timeout and timeout > 0.0 else self._MIN_CLIENT_TIMEOUT
            client_kwargs["timeout"] = client_timeout
        self._client = ModbusTcpClient(**client_kwargs)
        self.unit_id = unit_id
        self.timeout = timeout
        self.mapping: ModbusMap = deepcopy(mapping) if mapping else deepcopy(DEFAULT_MODBUS_MAP)

    def connect(self) -> bool:
        return bool(self._client.connect())

    def close(self) -> None:
        self._client.close()

    def state(self) -> str:
        return "connected" if self._client and self._client.connected else "disconnected"

    # Convenience read helpers
    def read_temperature(self) -> float:
        return self._read_float("temperature")

    def read_setpoint(self) -> float:
        return self._read_float("setpoint")

    def read_heating_power(self) -> float:
        return self._read_float("heating_power")

    def read_overload_flag(self) -> int:
        return int(self._read_decoded_register("overload"))

    def read_power_state(self) -> int:
        return int(self._read_coil("power_on"))

    # Write helpers
    def set_power_state(self, powered: bool) -> None:
        self._write_coil("power_on", bool(powered))

    def set_setpoint(self, value: float) -> None:
        self._write_float("setpoint", value)

    def set_ambient(self, value: float) -> None:
        self._write_float("ambient", value)

    def set_overload_threshold(self, value: float) -> None:
        self._write_float("overload_threshold", value)

    def set_overload_hysteresis(self, value: float) -> None:
        self._write_float("overload_hyst", value)

    # Internal Modbus helpers
    def _read_float(self, field: str) -> float:
        return float(self._read_decoded_register(field))

    def _write_float(self, field: str, value: float) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        registers = self._float_to_registers(value)
        self._ensure_connected()
        self._call_with_unit_kwarg("write_registers", address, registers)

    def _write_coil(self, field: str, value: bool) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        if config.get("kind", "coil") != "coil":
            raise ValueError(f"Field '{field}' is not configured as a coil")
        self._ensure_connected()
        self._call_with_unit_kwarg("write_coil", address, bool(value))

    def _read_coil(self, field: str) -> int:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        if config.get("kind", "coil") != "coil":
            raise ValueError(f"Field '{field}' is not configured as a coil")
        self._ensure_connected()
        result = self._call_with_unit_kwarg("read_coils", address, count=1)
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at coil {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at coil {address}")
        if not result.bits:
            raise RuntimeError(f"Modbus coil read returned empty result at {address}")
        return int(bool(result.bits[0]))

    def _read_decoded_register(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        if config.get("kind") == "coil":
            return float(self._read_coil(field_name))
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(f"Unsupported decoder '{decoder_key}' for field '{field_name}'")

        self._ensure_connected()
        result = self._call_with_unit_kwarg("read_holding_registers", address, count=decoder.count)
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at address {address}")
        return decoder.decode(result.registers)

    def _get_field_config(self, field_name: str) -> RegisterConfig:
        try:
            return self.mapping[field_name]
        except KeyError as exc:
            raise ValueError(f"Field '{field_name}' not found in Modbus map") from exc

    @staticmethod
    def _get_address(config: RegisterConfig, field_name: str) -> int:
        address = config.get("address")
        if isinstance(address, (list, tuple)):
            if not address:
                raise ValueError(f"Empty address list for field '{field_name}'")
            return int(address[0])
        if address is None:
            raise ValueError(f"Missing 'address' for field '{field_name}' in Modbus map")
        return int(address)

    def _ensure_connected(self) -> None:
        if not self._client:
            raise RuntimeError("Modbus client not initialised")
        if not getattr(self._client, "connected", False):
            if not self._client.connect():
                raise RuntimeError("Failed to connect Modbus client")

    @staticmethod
    def _float_to_registers(value: float) -> Tuple[int, int]:
        import struct

        packed = struct.pack(">f", value)
        return struct.unpack(">HH", packed)

    @staticmethod
    def modbus_to_float(data: Sequence[int], bit_order: str) -> float:
        import struct

        ordered = ModbusThermalControllerSUTExample._order_words(data, bit_order)
        packed = struct.pack(">HH", ordered[0], ordered[1])
        return struct.unpack(">f", packed)[0]

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
        ordered_bytes = [byte_map[ch] for ch in order]
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
