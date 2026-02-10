# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SCPI electronic load SUT client used by integration tests."""

from __future__ import annotations

import socket
import time
from typing import Optional


TERMINATOR = "\n"


class ScpiElectronicLoadSUTExample:
    """Very small helper bridging TCP sockets with SCPI commands."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5025,
        timeout: float = 0.2,
        debug: bool = False,
        reconnect_attempts: int = 3,
        reconnect_delay: float = 0.2,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self.reconnect_attempts = max(0, reconnect_attempts)
        self.reconnect_delay = max(0.0, reconnect_delay)
        self._socket: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        if self._socket is not None:
            return True
        try:
            self._connect()
        except OSError as exc:
            if self.debug:
                print(f"[SCPI CONNECT] failed: {exc!r}")
            return False
        return True

    def close(self) -> None:
        self._reset_socket()

    # ------------------------------------------------------------------
    # SCPI helpers
    # ------------------------------------------------------------------
    def write(self, command: str) -> None:
        payload = (command.rstrip("\r\n") + TERMINATOR).encode("ascii")
        last_exc: Optional[Exception] = None

        for attempt in range(self.reconnect_attempts + 1):
            try:
                sock = self._ensure_socket()
            except Exception as exc:
                last_exc = exc
                self._handle_socket_failure(exc)
            else:
                try:
                    if self.debug:
                        print(f"[SCPI WRITE] {payload!r}")
                    sock.sendall(payload)
                    return
                except (OSError, ConnectionError, RuntimeError, socket.timeout, TimeoutError) as exc:
                    last_exc = exc
                    self._handle_socket_failure(exc)

            if attempt < self.reconnect_attempts and self.reconnect_delay:
                time.sleep(self.reconnect_delay)

        raise RuntimeError(
            f"Failed to write SCPI command after {self.reconnect_attempts + 1} attempt(s)"
        ) from last_exc

    def read(self) -> str:
        sock = self._ensure_socket()
        buffer = bytearray()
        terminator = TERMINATOR.encode("ascii")
        while True:
            try:
                chunk = sock.recv(1024)
            except (OSError, ConnectionError, RuntimeError, socket.timeout, TimeoutError) as exc:
                self._handle_socket_failure(exc)
                raise
            if not chunk:
                self._handle_socket_failure(ConnectionError("SCPI connection closed during read"))
                raise ConnectionError("SCPI connection closed during read")
            buffer.extend(chunk)
            if buffer.endswith(terminator):
                break
        data = buffer.decode("ascii").strip()
        if self.debug:
            print(f"[SCPI READ] {data}")
        return data

    def query(self, command: str) -> str:
        last_exc: Optional[Exception] = None
        for attempt in range(self.reconnect_attempts + 1):
            try:
                self.write(command)
                return self.read()
            except (OSError, ConnectionError, RuntimeError, socket.timeout, TimeoutError) as exc:
                last_exc = exc
                if attempt < self.reconnect_attempts and self.reconnect_delay:
                    time.sleep(self.reconnect_delay)
        raise RuntimeError(
            f"Failed to complete SCPI query after {self.reconnect_attempts + 1} attempt(s)"
        ) from last_exc

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------
    def identify(self) -> str:
        return self.query("*IDN?")

    def set_mode(self, mode: str) -> None:
        self.write(f":SOURce:FUNCtion {mode}")

    def mode(self) -> str:
        return self.query(":SOURce:FUNCtion?")

    def input_on(self) -> None:
        self.write(":SOURce:INPut:STATe ON")

    def input_off(self) -> None:
        self.write(":SOURce:INPut:STATe OFF")

    def input_state(self) -> int:
        return int(float(self.query(":SOURce:INPut:STATe?")))

    def set_current(self, value: float) -> None:
        self.write(f":SOURce:CURRent:LEVel:IMMediate {value}")

    def current_setpoint(self) -> float:
        return float(self.query(":SOURce:CURRent:LEVel:IMMediate?"))

    def set_voltage(self, value: float) -> None:
        self.write(f":SOURce:VOLTage:LEVel:IMMediate {value}")

    def voltage_setpoint(self) -> float:
        return float(self.query(":SOURce:VOLTage:LEVel:IMMediate?"))

    def set_power(self, value: float) -> None:
        self.write(f":SOURce:POWer:LEVel:IMMediate {value}")

    def power_setpoint(self) -> float:
        return float(self.query(":SOURce:POWer:LEVel:IMMediate?"))

    def set_resistance(self, value: float) -> None:
        self.write(f":SOURce:RESistance:LEVel:IMMediate {value}")

    def resistance_setpoint(self) -> float:
        return float(self.query(":SOURce:RESistance:LEVel:IMMediate?"))

    def measure_current(self) -> float:
        return float(self.query(":MEASure:CURRent?"))

    def measure_voltage(self) -> float:
        return float(self.query(":MEASure:VOLTage?"))

    def measure_power(self) -> float:
        return float(self.query(":MEASure:POWer?"))

    def measure_resistance(self) -> float:
        return float(self.query(":MEASure:RESistance?"))

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RuntimeError("SCPI client is not connected")
        return self._socket

    def _ensure_socket(self) -> socket.socket:
        if self._socket is None:
            self._connect()
        return self._require_socket()

    def _connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._socket = sock

    def _reset_socket(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def _handle_socket_failure(self, exc: Exception) -> None:
        if self.debug:
            print(f"[SCPI SOCKET] failure: {exc!r}")
        self._reset_socket()


__all__ = ["ScpiElectronicLoadSUTExample"]
