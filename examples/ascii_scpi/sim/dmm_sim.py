# SPDX-License-Identifier: MIT
"""Simple SCPI digital multimeter simulator."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Optional

from .common import BaseScpiDevice, add_common_args, clamp, format_float, run_server


@dataclass
class DmmState:
    mode: str = "VOLT:DC"
    range_v: float = 10.0
    voltage: float = 1.234
    resistance: float = 1000.0


class ScpiDmmDevice(BaseScpiDevice):
    def __init__(self, idn: str) -> None:
        super().__init__(idn)
        self.state = DmmState()
        self._rng = random.Random(2026)

    def _next_voltage(self) -> float:
        drift = self._rng.uniform(-0.05, 0.05)
        value = clamp(self.state.voltage + drift, -self.state.range_v, self.state.range_v)
        self.state.voltage = value
        return value

    def _next_resistance(self) -> float:
        drift = self._rng.uniform(-5.0, 5.0)
        value = clamp(self.state.resistance + drift, 10.0, 100000.0)
        self.state.resistance = value
        return value

    def handle_device_command(self, command: str) -> Optional[str]:
        cmd = command.strip()
        upper = cmd.upper()

        if upper.startswith("CONF:VOLT:DC"):
            parts = cmd.split()
            self.state.mode = "VOLT:DC"
            if len(parts) >= 2:
                try:
                    self.state.range_v = float(parts[1])
                except ValueError:
                    self.record_error()
            return None

        if upper == "MEAS:VOLT:DC?":
            return format_float(self._next_voltage())
        if upper == "MEAS:RES?":
            return format_float(self._next_resistance(), digits=2)
        if upper == "READ?":
            if self.state.mode == "VOLT:DC":
                return format_float(self._next_voltage())
            return format_float(self._next_resistance(), digits=2)

        self.record_error()
        if cmd.endswith("?"):
            return self.errors.pop()
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SCPI DMM simulator")
    add_common_args(parser)
    parser.add_argument(
        "--idn",
        default="SPX,SCPI_DMM_SIM,DMM0001,1.0",
        help="IDN string returned by *IDN?",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    device = ScpiDmmDevice(args.idn)
    run_server(
        device,
        host=args.host,
        port=args.port,
        terminator=args.terminator,
        serial_port=args.serial_port,
        baud=args.baud,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
    )


if __name__ == "__main__":
    main()
