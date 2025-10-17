"""Shared helpers for Modbus-backed SUT example drivers."""
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

try:
    from pymodbus.exceptions import ConnectionException, ModbusIOException  # type: ignore
except Exception:  # pragma: no cover - fallback when pymodbus unavailable
    class ModbusIOException(Exception):  # type: ignore
        pass

    class ConnectionException(ModbusIOException):  # type: ignore
        pass

RegisterConfig = Dict[str, Any]
ModbusMap = Dict[str, RegisterConfig]


@dataclass(frozen=True)
class RegisterDecoder:
    count: int
    fn: Callable[[Sequence[int]], Any]

    def decode(self, registers: Sequence[int]) -> Any:
        if len(registers) != self.count:
            raise ValueError(f"Decoder expected {self.count} registers, got {len(registers)}")
        return self.fn(registers)


class ModbusSUTBase:
    """Common client plumbing for Modbus-based SUT example drivers."""

    _MIN_CLIENT_TIMEOUT = 0.05

    def __init__(
        self,
        *,
        default_map: ModbusMap,
        mapping: Optional[ModbusMap] = None,
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        timeout: Optional[float] = 2.0,
    ) -> None:
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise RuntimeError(
                "pymodbus is not available. Install pymodbus to use Modbus SUT examples."
            )
        client_kwargs = {"host": host, "port": port}
        if timeout is not None:
            client_timeout = timeout if timeout and timeout > 0.0 else self._MIN_CLIENT_TIMEOUT
            client_kwargs["timeout"] = client_timeout
        self._client = ModbusTcpClient(**client_kwargs)
        self.unit_id = unit_id
        self.timeout = timeout
        self.mapping: ModbusMap = self._merge_mapping(default_map, mapping)

    @staticmethod
    def _merge_mapping(default_map: ModbusMap, overrides: Optional[ModbusMap]) -> ModbusMap:
        merged = deepcopy(default_map)
        if overrides:
            for key, value in overrides.items():
                merged[key] = deepcopy(value)
        return merged

    # Connection helpers -------------------------------------------------
    def connect(self) -> bool:
        return bool(self._client.connect())

    def close(self) -> None:
        self._client.close()

    def _ensure_connected(self) -> None:
        if not self._client:
            raise RuntimeError("Modbus client not initialised")
        if not getattr(self._client, "connected", False):
            if not self._client.connect():
                raise RuntimeError("Failed to connect Modbus client")

    def _call_with_unit_kwarg(self, method_name: str, *args, **kwargs):
        method = getattr(self._client, method_name)
        try:
            return method(*args, slave=self.unit_id, **kwargs)
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" in message and "'slave'" in message:
                return method(*args, unit=self.unit_id, **kwargs)
            raise

    # Mapping helpers ----------------------------------------------------
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

    # Modbus data helpers ------------------------------------------------
    @staticmethod
    def _float_to_registers(value: float) -> Tuple[int, int]:
        import struct

        packed = struct.pack(">f", value)
        return struct.unpack(">HH", packed)

    @staticmethod
    def modbus_to_float(data: Sequence[int], bit_order: str) -> float:
        import struct

        ordered = ModbusSUTBase._order_words(data, bit_order)
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
        try:
            ordered_bytes = [byte_map[ch] for ch in order]
        except KeyError as exc:  # pragma: no cover - defensive mapping guard
            raise ValueError(
                f"Unsupported bit order '{bit_order}' for Modbus float decoding"
            ) from exc
        word0 = (ordered_bytes[0] << 8) | ordered_bytes[1]
        word1 = (ordered_bytes[2] << 8) | ordered_bytes[3]
        return (word0, word1)

    # Generic read helpers -----------------------------------------------
    def _read_holding_registers(self, address: int, count: int):
        self._ensure_connected()
        result = self._call_with_unit_kwarg("read_holding_registers", address, count=count)
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at address {address}")
        return result.registers

    def _read_coils(self, address: int, count: int = 1):
        self._ensure_connected()
        result = self._call_with_unit_kwarg("read_coils", address, count=count)
        if result is None:
            raise RuntimeError(f"Modbus read returned no response at coil {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus coil read failed at address {address}")
        return result.bits

    def _write_coils(self, address: int, value: bool) -> None:
        self._ensure_connected()
        self._call_with_unit_kwarg("write_coil", address, bool(value))

    def _write_registers(self, address: int, registers: Sequence[int]) -> None:
        self._ensure_connected()
        self._call_with_unit_kwarg("write_registers", address, registers)


__all__ = [
    "ConnectionException",
    "ModbusIOException",
    "ModbusMap",
    "ModbusSUTBase",
    "ModbusTcpClient",
    "RegisterConfig",
    "RegisterDecoder",
]
