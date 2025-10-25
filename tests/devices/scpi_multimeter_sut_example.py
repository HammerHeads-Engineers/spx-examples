# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Example SCPI multimeter SUT client used by integration tests."""

from __future__ import annotations

import socket
from typing import Optional


TERMINATOR = "\n"


class ScpiMultimeterSUTExample:
    """Very small helper bridging TCP sockets with SCPI commands."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5025,
        timeout: float = 2.0,
        debug: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self._socket: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        if self._socket is not None:
            return True
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._socket = sock
        return True

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    # ------------------------------------------------------------------
    # SCPI helpers
    # ------------------------------------------------------------------
    def write(self, command: str) -> None:
        sock = self._require_socket()
        payload = (command.rstrip("\r\n") + TERMINATOR).encode("ascii")
        if self.debug:
            print(f"[SCPI WRITE] {payload!r}")
        sock.sendall(payload)

    def read(self) -> str:
        sock = self._require_socket()
        buffer = bytearray()
        terminator = TERMINATOR.encode("ascii")
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break
            buffer.extend(chunk)
            if buffer.endswith(terminator):
                break
        data = buffer.decode("ascii").strip()
        if self.debug:
            print(f"[SCPI READ] {data}")
        return data

    def query(self, command: str) -> str:
        self.write(command)
        return self.read()

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------
    def measure_voltage(self) -> float:
        return float(self.query("MEAS:VOLT?"))

    def measure_current(self) -> float:
        return float(self.query("MEAS:CURR?"))

    def configure_voltage(self, value: float) -> str:
        return self.query(f"CONF:VOLT {value}")

    def configure_current(self, value: float) -> str:
        return self.query(f"CONF:CURR {value}")

    def system_version(self) -> str:
        return self.query("SYST:VERS?")

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RuntimeError("SCPI client is not connected")
        return self._socket


__all__ = ["ScpiMultimeterSUTExample"]
