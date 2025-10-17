"""Example SUT implementation: Modbus vacuum gauge client used in integration tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

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
    "rough_pressure": {
        "address": 0,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "high_pressure": {
        "address": 2,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "ionizer_enabled": {"address": 4, "kind": "coil"},
    "ionizer_available": {"address": 5, "decoder": "u16"},
    "ionizer_interlock": {"address": 6, "decoder": "u16"},
    "leak_event": {"address": 7, "kind": "coil"},
    "pumpdown_target": {
        "address": 8,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "upset_target": {
        "address": 10,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "discharge_event": {"address": 27, "kind": "coil"},
    "discharge_pressure": {
        "address": 28,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
    "discharge_decay": {
        "address": 30,
        "decoder": "modbus_float_be",
        "bit_order": "ABCD",
    },
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


def _decode_float_abcd(registers: Sequence[int]) -> float:
    return ModbusVacuumGaugeSUTExample.modbus_to_float(registers, "ABCD")


class ModbusVacuumGaugeSUTExample:
    """Thin wrapper around pymodbus representing the SUT Modbus vacuum gauge model."""

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
                "pymodbus is not available. Install pymodbus to use ModbusVacuumGaugeSUTExample."
            )
        client_kwargs = {"host": host, "port": port}
        if timeout is not None:
            client_timeout = (
                timeout if timeout and timeout > 0.0 else self._MIN_CLIENT_TIMEOUT
            )
            client_kwargs["timeout"] = client_timeout
        self._client = ModbusTcpClient(**client_kwargs)
        self.unit_id = unit_id
        self.timeout = timeout
        self.mapping: ModbusMap = deepcopy(mapping) if mapping else deepcopy(
            DEFAULT_MODBUS_MAP
        )

    def connect(self) -> bool:
        return bool(self._client.connect())

    def close(self) -> None:
        self._client.close()

    def read_pressure(self, field: str) -> float:
        return float(self._read_decoded_register(field))

    def read_rough_pressure(self) -> float:
        return self.read_pressure("rough_pressure")

    def read_high_pressure(self) -> float:
        return self.read_pressure("high_pressure")

    def read_flag(self, field: str) -> int:
        return int(self._read_decoded_register(field))

    def set_coil(self, field: str, value: int) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        self._ensure_connected()
        self._call_with_unit_kwarg("write_coil", address, bool(value))

    def set_float(self, field: str, value: float) -> None:
        config = self._get_field_config(field)
        address = self._get_address(config, field)
        registers = self._float_to_registers(value)
        self._ensure_connected()
        self._call_with_unit_kwarg("write_registers", address, registers)

    def _read_decoded_register(self, field_name: str) -> float:
        config = self._get_field_config(field_name)
        address = self._get_address(config, field_name)
        decoder_key = config.get("decoder", "u16")
        decoder = self._DECODER_REGISTRY.get(decoder_key)
        if decoder is None:
            raise ValueError(
                f"Unsupported decoder '{decoder_key}' for field '{field_name}'"
            )

        self._ensure_connected()
        result = self._call_with_unit_kwarg(
            "read_holding_registers", address, count=decoder.count
        )
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at address {address}")
        return decoder.decode(result.registers)

    @staticmethod
    def _float_to_registers(value: float) -> Sequence[int]:
        import struct

        packed = struct.pack(">f", value)
        return struct.unpack(">HH", packed)

    @staticmethod
    def modbus_to_float(data: Sequence[int], bit_order: str) -> float:
        import struct

        ordered = ModbusVacuumGaugeSUTExample._order_words(data, bit_order)
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
            raise ValueError(
                f"Unsupported bit order '{bit_order}' for Modbus float decoding"
            )
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

    def _get_field_config(self, field_name: str) -> RegisterConfig:
        try:
            return self.mapping[field_name]
        except KeyError as exc:
            raise ValueError(f"Field '{field_name}' not found in Modbus map") from exc

    def _get_address(self, config: RegisterConfig, field_name: str) -> int:
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
