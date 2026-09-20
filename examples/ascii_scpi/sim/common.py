# SPDX-License-Identifier: MIT
"""Shared ASCII/SCPI simulator helpers."""

from __future__ import annotations

import argparse
import socketserver
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_TERMINATOR = "\n"
DEFAULT_ERROR = '0,"No error"'
UNDEFINED_HEADER = '-113,"Undefined header"'


@dataclass
class ErrorQueue:
    max_depth: int = 10
    _queue: list[str] = field(default_factory=list)

    def push(self, message: str) -> None:
        if len(self._queue) >= self.max_depth:
            self._queue.pop(0)
        self._queue.append(message)

    def pop(self) -> str:
        if self._queue:
            return self._queue.pop(0)
        return DEFAULT_ERROR

    def clear(self) -> None:
        self._queue.clear()


class BaseScpiDevice:
    idn: str

    def __init__(self, idn: str) -> None:
        self.idn = idn
        self.errors = ErrorQueue()
        self._lock = threading.Lock()

    def handle_command(self, command: str) -> Optional[str]:
        cmd = command.strip()
        if not cmd:
            return None

        normalized = cmd.upper()
        if normalized == "*IDN?":
            return self.idn
        if normalized == "*CLS":
            self.errors.clear()
            return None
        if normalized == "SYST:ERR?":
            return self.errors.pop()

        return self.handle_device_command(cmd)

    def handle_device_command(self, command: str) -> Optional[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def record_error(self, message: str = UNDEFINED_HEADER) -> None:
        self.errors.push(message)


class ScpiTcpHandler(socketserver.BaseRequestHandler):
    device: BaseScpiDevice
    terminator: str
    timeout_s: float

    def handle(self) -> None:
        sock = self.request
        sock.settimeout(self.timeout_s)
        buffer = ""
        terminator = self.terminator
        while True:
            try:
                data = sock.recv(1024)
            except TimeoutError:
                continue
            except OSError:
                break
            if not data:
                break
            try:
                chunk = data.decode("ascii", errors="ignore")
            except UnicodeDecodeError:
                continue
            buffer += chunk
            while terminator in buffer:
                line, buffer = buffer.split(terminator, 1)
                line = line.rstrip("\r\n")
                response = self.device.handle_command(line)
                if response is not None:
                    payload = f"{response}{terminator}".encode("ascii")
                    try:
                        sock.sendall(payload)
                    except OSError:
                        return


class ScpiTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        device: BaseScpiDevice,
        terminator: str = DEFAULT_TERMINATOR,
        timeout_s: float = 1.0,
    ) -> None:
        self.device = device
        self.terminator = terminator
        self.timeout_s = timeout_s
        super().__init__(address, self._handler_factory())

    def _handler_factory(self):
        device = self.device
        terminator = self.terminator
        timeout_s = self.timeout_s

        class Handler(ScpiTcpHandler):
            pass

        Handler.device = device
        Handler.terminator = terminator
        Handler.timeout_s = timeout_s
        return Handler


@dataclass
class SerialConfig:
    port: str
    baud: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout_s: float = 1.0


class SerialScpiRunner:
    def __init__(self, device: BaseScpiDevice, config: SerialConfig, terminator: str) -> None:
        self.device = device
        self.config = config
        self.terminator = terminator

    def run(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise SystemExit("pyserial is required for serial mode") from exc

        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        ser = serial.Serial(
            port=self.config.port,
            baudrate=self.config.baud,
            bytesize=self.config.bytesize,
            parity=parity_map.get(self.config.parity.upper(), serial.PARITY_NONE),
            stopbits=self.config.stopbits,
            timeout=self.config.timeout_s,
        )
        with ser:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="ignore").rstrip("\r\n")
                response = self.device.handle_command(line)
                if response is None:
                    continue
                payload = f"{response}{self.terminator}".encode("ascii")
                ser.write(payload)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for TCP mode")
    parser.add_argument("--port", type=int, default=5025, help="Bind port for TCP mode")
    parser.add_argument(
        "--terminator",
        default=DEFAULT_TERMINATOR,
        help="Line terminator (default: \\n)",
    )
    parser.add_argument(
        "--serial",
        dest="serial_port",
        default=None,
        help="Serial port device (enables serial mode)",
    )
    parser.add_argument("--baud", type=int, default=9600, help="Serial baudrate")
    parser.add_argument("--bytesize", type=int, default=8, help="Serial byte size")
    parser.add_argument("--parity", default="N", help="Serial parity (N/E/O/M/S)")
    parser.add_argument("--stopbits", type=int, default=1, help="Serial stop bits")


def run_server(
    device: BaseScpiDevice,
    *,
    host: str,
    port: int,
    terminator: str,
    serial_port: Optional[str],
    baud: int,
    bytesize: int,
    parity: str,
    stopbits: int,
) -> None:
    if serial_port:
        config = SerialConfig(
            port=serial_port,
            baud=baud,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
        )
        SerialScpiRunner(device, config, terminator).run()
        return

    server = ScpiTcpServer((host, port), device=device, terminator=terminator)
    print(f"SCPI simulator listening on {host}:{port} (terminator={terminator!r})")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def format_float(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def jitter(value: float, amplitude: float) -> float:
    if amplitude <= 0.0:
        return value
    return value + (amplitude * (2 * (time.time() % 1.0) - 1.0))
