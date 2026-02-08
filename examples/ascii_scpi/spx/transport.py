"""Thin ASCII/SCPI transport used by the example scripts."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SerialSettings:
    port: str = ""
    baud: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1


@dataclass
class TransportConfig:
    mode: str = "tcp"
    host: str = "127.0.0.1"
    port: int = 5025
    terminator: str = "\n"
    timeout_ms: int = 500
    serial: SerialSettings = field(default_factory=SerialSettings)


def load_config(path: str | Path) -> TransportConfig:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    serial_doc = doc.get("serial") or {}
    return TransportConfig(
        mode=str(doc.get("mode", "tcp")),
        host=str(doc.get("host", "127.0.0.1")),
        port=int(doc.get("port", 5025)),
        terminator=str(doc.get("terminator", "\n")),
        timeout_ms=int(doc.get("timeout_ms", 500)),
        serial=SerialSettings(
            port=str(serial_doc.get("port", "")),
            baud=int(serial_doc.get("baud", 9600)),
            bytesize=int(serial_doc.get("bytesize", 8)),
            parity=str(serial_doc.get("parity", "N")),
            stopbits=int(serial_doc.get("stopbits", 1)),
        ),
    )


class AsciiScpiTransport:
    def __init__(self, config: TransportConfig) -> None:
        self.config = config
        self._socket: Optional[socket.socket] = None
        self._serial = None

    def open(self) -> None:
        if self.config.mode == "serial":
            self._open_serial()
            return
        self._open_tcp()

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def write(self, command: str) -> None:
        payload = self._encode(command)
        if self._serial is not None:
            self._serial.write(payload)
            return
        sock = self._require_socket()
        sock.sendall(payload)

    def read(self) -> str:
        terminator = self.config.terminator.encode("ascii")
        if self._serial is not None:
            return self._read_serial(terminator)
        sock = self._require_socket()
        buffer = bytearray()
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                raise RuntimeError("SCPI socket closed during read")
            buffer.extend(chunk)
            if buffer.endswith(terminator):
                break
        return buffer.decode("ascii").strip()

    def query(self, command: str) -> str:
        self.write(command)
        return self.read()

    def _encode(self, command: str) -> bytes:
        return (command.rstrip("\r\n") + self.config.terminator).encode("ascii")

    def _open_tcp(self) -> None:
        sock = socket.create_connection(
            (self.config.host, self.config.port),
            timeout=self.config.timeout_ms / 1000.0,
        )
        sock.settimeout(self.config.timeout_ms / 1000.0)
        self._socket = sock

    def _open_serial(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pyserial is required for serial mode") from exc

        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        self._serial = serial.Serial(
            port=self.config.serial.port,
            baudrate=self.config.serial.baud,
            bytesize=self.config.serial.bytesize,
            parity=parity_map.get(self.config.serial.parity.upper(), serial.PARITY_NONE),
            stopbits=self.config.serial.stopbits,
            timeout=self.config.timeout_ms / 1000.0,
        )

    def _read_serial(self, terminator: bytes) -> str:
        deadline = time.time() + (self.config.timeout_ms / 1000.0)
        buffer = bytearray()
        while time.time() < deadline:
            chunk = self._serial.read(1)
            if not chunk:
                continue
            buffer.extend(chunk)
            if buffer.endswith(terminator):
                break
        if not buffer:
            raise RuntimeError("Timed out waiting for serial response")
        return buffer.decode("ascii").strip()

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RuntimeError("ASCII transport not connected")
        return self._socket
