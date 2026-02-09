"""Simple SCPI bench power supply simulator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional

from .common import BaseScpiDevice, add_common_args, format_float, run_server


@dataclass
class PsuState:
    voltage_set: float = 5.0
    current_set: float = 1.0
    output_on: bool = False


class ScpiPsuDevice(BaseScpiDevice):
    def __init__(self, idn: str) -> None:
        super().__init__(idn)
        self.state = PsuState()

    def handle_device_command(self, command: str) -> Optional[str]:
        cmd = command.strip()
        upper = cmd.upper()

        if upper.startswith("SOUR:VOLT"):
            parts = cmd.split()
            if upper.endswith("?"):
                return format_float(self.state.voltage_set)
            if len(parts) < 2:
                self.record_error()
                return None
            try:
                self.state.voltage_set = float(parts[1])
            except ValueError:
                self.record_error()
            return None

        if upper.startswith("SOUR:CURR"):
            parts = cmd.split()
            if upper.endswith("?"):
                return format_float(self.state.current_set)
            if len(parts) < 2:
                self.record_error()
                return None
            try:
                self.state.current_set = float(parts[1])
            except ValueError:
                self.record_error()
            return None

        if upper == "MEAS:VOLT?":
            voltage = self.state.voltage_set if self.state.output_on else 0.0
            return format_float(voltage)
        if upper == "MEAS:CURR?":
            current = self.state.current_set if self.state.output_on else 0.0
            return format_float(current)

        if upper == "OUTP?":
            return "ON" if self.state.output_on else "OFF"
        if upper.startswith("OUTP"):
            parts = upper.split()
            if len(parts) < 2:
                self.record_error()
                return None
            if parts[1] == "ON":
                self.state.output_on = True
                return None
            if parts[1] == "OFF":
                self.state.output_on = False
                return None
            self.record_error()
            return None

        self.record_error()
        if cmd.endswith("?"):
            return self.errors.pop()
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SCPI PSU simulator")
    add_common_args(parser)
    parser.add_argument(
        "--idn",
        default="SPX,SCPI_PSU_SIM,PSU0001,1.0",
        help="IDN string returned by *IDN?",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    device = ScpiPsuDevice(args.idn)
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
