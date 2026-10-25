# SPDX-License-Identifier: MIT
"""Set PSU voltage/current via SCPI using the SPX-hosted model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from examples.ascii_scpi.spx.spx_utils import (
    ensure_instance,
    ensure_model,
    load_model_definition,
    wait_for_ascii_port,
)
from examples.ascii_scpi.spx.transport import AsciiScpiTransport, TransportConfig


MODEL_KEY = "examples_scpi_psu"
INSTANCE_KEY = "examples_scpi_psu"
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "scpi_psu.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voltage", type=float, default=5.0, help="Voltage setpoint")
    parser.add_argument("--current", type=float, default=1.0, help="Current limit")
    parser.add_argument("--output", choices=("on", "off"), default="on", help="Output state")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        import spx_python  # type: ignore
    except ImportError as exc:
        raise SystemExit(f"spx_python is required: {exc}") from exc

    product_key = os.environ.get("SPX_PRODUCT_KEY")
    if not product_key:
        raise SystemExit("SPX_PRODUCT_KEY must be set")

    base_url = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
    client = spx_python.init(address=base_url, product_key=product_key)
    model_def = load_model_definition(MODEL_PATH)
    changed = ensure_model(client, MODEL_KEY, model_def)
    instance = ensure_instance(client, INSTANCE_KEY, MODEL_KEY, recreate=changed, start=True)

    port = wait_for_ascii_port(instance)
    config = TransportConfig(host="127.0.0.1", port=port)
    transport = AsciiScpiTransport(config)
    transport.open()
    try:
        transport.query("*IDN?")
        transport.write(f"SOUR:VOLT {args.voltage}")
        transport.write(f"SOUR:CURR {args.current}")
        transport.write(f"OUTP {args.output.upper()}")
        v = transport.query("MEAS:VOLT?")
        i = transport.query("MEAS:CURR?")
    finally:
        transport.close()

    print(f"Voltage set to {args.voltage} V, measured {v} V")
    print(f"Current set to {args.current} A, measured {i} A")


if __name__ == "__main__":
    main()
