# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Smoke coverage for the ASCII/SCPI example models (PSU + DMM)."""

from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.repo import repo_root
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds


ROOT = repo_root()
PSU_MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "generic"
    / "bench_power_supply__scpi.yaml"
)
DMM_MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "generic"
    / "digital_multimeter__scpi.yaml"
)

PSU_MODEL_KEY = "tests__scpi_bench_psu"
DMM_MODEL_KEY = "tests__scpi_digital_dmm"
PSU_INSTANCE_KEY = "tests_scpi_bench_psu"
DMM_INSTANCE_KEY = "tests_scpi_digital_dmm"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class SimpleScpiClient:
    def __init__(self, host: str, port: int, timeout: float = 0.5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._socket = sock

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def write(self, command: str) -> None:
        payload = (command.rstrip("\r\n") + "\n").encode("ascii")
        self._require_socket().sendall(payload)

    def query(self, command: str) -> str:
        self.write(command)
        buffer = bytearray()
        while True:
            chunk = self._require_socket().recv(1024)
            if not chunk:
                raise ConnectionError("SCPI connection closed during read")
            buffer.extend(chunk)
            if buffer.endswith(b"\n"):
                break
        return buffer.decode("ascii").strip()

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RuntimeError("SCPI client not connected")
        return self._socket


class TestAsciiScpiExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run ASCII/SCPI tests.")

        cls._spx = spx_python
        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)

        _, cls._psu_instance, _ = bootstrap_model_instance(
            spx_python,
            product_key=product_key,
            base_url=SPX_BASE_URL,
            model_path=PSU_MODEL_PATH,
            model_key=PSU_MODEL_KEY,
            instance_key=PSU_INSTANCE_KEY,
        )
        _, cls._dmm_instance, _ = bootstrap_model_instance(
            spx_python,
            product_key=product_key,
            base_url=SPX_BASE_URL,
            model_path=DMM_MODEL_PATH,
            model_key=DMM_MODEL_KEY,
            instance_key=DMM_INSTANCE_KEY,
        )

    def setUp(self) -> None:
        self.psu_instance = getattr(self.__class__, "_psu_instance", None)
        self.dmm_instance = getattr(self.__class__, "_dmm_instance", None)
        if self.psu_instance is None or self.dmm_instance is None:
            self.skipTest("ASCII/SCPI instances not initialised")

        try:
            psu_comm = self.psu_instance["communication"]["ascii"]
            attach = getattr(psu_comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass
        try:
            dmm_comm = self.dmm_instance["communication"]["ascii"]
            attach = getattr(dmm_comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass

        self.psu_port = wait_for_ascii_port(self.psu_instance, timeout=10.0, interval=0.2)
        self.dmm_port = wait_for_ascii_port(self.dmm_instance, timeout=10.0, interval=0.2)

    def test_psu_basic_cycle(self):
        client = SimpleScpiClient("127.0.0.1", self.psu_port)
        client.connect()
        try:
            client.write("SOUR:VOLT 7.5")
            client.write("SOUR:CURR 0.4")
            client.write("OUTP ON")
            wait_seconds(0.1)
            voltage = float(client.query("MEAS:VOLT?"))
            current = float(client.query("MEAS:CURR?"))
        finally:
            client.close()

        self.assertAlmostEqual(voltage, 7.5, places=2)
        self.assertAlmostEqual(current, 0.4, places=2)

    def test_dmm_basic_cycle(self):
        client = SimpleScpiClient("127.0.0.1", self.dmm_port)
        client.connect()
        try:
            client.write("CONF:VOLT:DC 10")
            voltage = float(client.query("MEAS:VOLT:DC?"))
            readback = float(client.query("READ?"))
        finally:
            client.close()

        self.assertTrue(-10.0 <= voltage <= 10.0)
        self.assertTrue(-10.0 <= readback <= 10.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
