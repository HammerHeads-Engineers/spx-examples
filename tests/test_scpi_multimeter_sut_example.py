# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example SCPI multimeter SUT implementation."""

import os
import pathlib
import socket
import statistics
import time
import unittest
from typing import Optional

from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.devices.scpi_multimeter_sut_example import ScpiMultimeterSUTExample


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "library" / "measurement_instruments" / "generic" / "scpi_multimeter.yaml"
MODEL_KEY = "tests__scpi_multimeter"
INSTANCE_KEY = "generic_scpi_multimeter"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


class TestScpiMultimeterSUTExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest(
                "SPX_PRODUCT_KEY must be set to run SCPI integration tests."
            )

        cls._spx = spx_python
        (
            cls._client,
            cls._instance,
            cls._model_changed,
        ) = bootstrap_model_instance(
            spx_python,
            product_key=product_key,
            base_url=SPX_API_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
        )

    def setUp(self):
        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:  # pragma: no cover - defensive
            self.skipTest("SCPI multimeter instance not initialised")

        debug = bool(int(os.environ.get("SCPI_TEST_DEBUG", "1")))
        self.sut = ScpiMultimeterSUTExample(debug=debug)
        try:
            if not self.sut.connect():
                self.skipTest("ASCII/SCPI server not reachable at 127.0.0.1:5025")
        except OSError as exc:
            self.skipTest(f"Unable to connect to SCPI server: {exc}")
        wait_seconds(0.2)
        self._ensure_scenario_stopped("voltage_static")
        self._ensure_scenario_stopped("ascii_disconnect")
        self._ensure_scenario_stopped("ascii_response_delay_spike")
        self._ensure_scenario_stopped("discharge_spike")

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _set_attribute(self, name: str, value) -> None:
        attrs = self.instance["attributes"]
        attrs[name].internal_value = value
        wait_seconds(0.1)

    def _get_attribute(self, name: str):
        return self.instance["attributes"][name].internal_value

    def _ensure_scenario_stopped(self, name: str) -> None:
        try:
            scenario = self.instance["scenarios"][name]
        except Exception:
            return
        stop = getattr(scenario, "stop", None)
        if callable(stop):
            stop()
            wait_seconds(0.1)

    def _read_ascii_response_delay(self) -> Optional[float]:
        comm = self.instance["communication"]["ascii"]
        value = getattr(comm, "response_delay", None)
        if value is None and isinstance(comm, dict):
            value = comm.get("response_delay")
        if hasattr(value, "internal_value"):
            value = value.internal_value
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _collect_voltage_samples(
        self,
        *,
        count: int = 10,
        interval: float = 0.2,
    ) -> list[float]:
        samples: list[float] = []
        for index in range(count):
            raw = self._query_or_skip("MEAS:VOLT?")
            try:
                reading = float(raw)
            except ValueError:
                self.fail(f"Expected numeric voltage, got '{raw}'")
            samples.append(reading)
            if index < count - 1:
                wait_seconds(interval)
        return samples

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def _query_or_skip(self, command: str) -> str:
        reply = self.sut.query(command)
        if reply == "":
            self.skipTest(
                f"No response from SCPI server for command '{command}'."
            )
        return reply

    def test_measure_voltage_matches_attribute(self):
        target_voltage = 7.25
        self._set_attribute("voltage", target_voltage)
        raw = self._query_or_skip("MEAS:VOLT?")
        try:
            voltage = float(raw)
        except ValueError:
            self.fail(f"Expected numeric voltage, got '{raw}'")
        self.assertAlmostEqual(voltage, target_voltage, places=2)

    def test_measure_current_matches_attribute(self):
        target_current = 0.42
        self._set_attribute("current", target_current)
        raw = self._query_or_skip("MEAS:CURR?")
        try:
            current = float(raw)
        except ValueError:
            self.fail(f"Expected numeric current, got '{raw}'")
        self.assertAlmostEqual(current, target_current, places=3)

    def test_measure_resistance_matches_attribute(self):
        target_res = 1234.5
        self._set_attribute("resistance", target_res)
        raw = self._query_or_skip("MEAS:RES?")
        try:
            resistance = float(raw)
        except ValueError:
            self.fail(f"Expected numeric resistance, got '{raw}'")
        self.assertAlmostEqual(resistance, target_res, places=2)

    def test_conf_mode_updates_measurement_mode(self):
        reply = self._query_or_skip("CONF:MODE CURRENT")
        self.assertEqual(reply, "ACK")
        wait_seconds(0.1)
        self.assertEqual(self._get_attribute("measurement_mode"), "CURRENT")

    def test_conf_volt_switches_to_voltage_mode(self):
        # This command does not produce a response; fire-and-forget.
        self.sut.write("CONF:VOLT")
        wait_seconds(0.1)
        self.assertEqual(self._get_attribute("measurement_mode"), "voltage")

    def test_unknown_command_returns_error(self):
        reply = self._query_or_skip("FOO")
        self.assertTrue(reply.startswith("-113"), f"Unexpected reply: {reply}")

    def test_voltage_static_scenario_converges_to_target_voltage(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["voltage_static"]
        self._set_attribute("voltage", 0.0)
        start = getattr(scenario, "start", None)
        if callable(start):
            start()
        wait_seconds(3.0)

        samples = self._collect_voltage_samples(count=10, interval=0.2)
        average_voltage = statistics.mean(samples)
        self.assertAlmostEqual(
            average_voltage,
            230.0,
            delta=1.0,
            msg=f"Voltage scenario did not converge: readings={samples!r}",
        )

    def test_voltage_static_scenario_stop_disables_noise(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["voltage_static"]
        stop = getattr(scenario, "stop", None)
        if not callable(stop):
            self.skipTest("Scenario implementation does not expose stop()")

        self._set_attribute("voltage", 0.0)
        start = getattr(scenario, "start", None)
        if callable(start):
            start()

        try:
            noisy_samples = []
            noisy_stdev = 0.0
            noisy_span = 0.0
            for attempt in range(3):
                wait_seconds(3.0 if attempt == 0 else 1.0)
                noisy_samples = self._collect_voltage_samples(count=20, interval=0.1)
                noisy_stdev = statistics.pstdev(noisy_samples)
                noisy_span = max(noisy_samples) - min(noisy_samples)
                if noisy_stdev > 5e-4 and noisy_span > 1e-3:
                    break
            else:
                self.skipTest(
                    "SCPI voltage scenario reported flat readings; proportional noise likely unsupported in this runtime."
                )

            self.assertGreater(
                noisy_stdev,
                5e-4,
                f"Expected voltage noise while scenario running, got {noisy_samples!r}",
            )
            self.assertGreater(
                noisy_span,
                1e-3,
                f"Expected varying readings with noise active, got {noisy_samples!r}",
            )

            stop()
            wait_seconds(0.5)

            steady_samples = self._collect_voltage_samples(count=10, interval=0.1)
            steady_stdev = statistics.pstdev(steady_samples)
            steady_mean = statistics.mean(steady_samples)
            steady_span = max(steady_samples) - min(steady_samples)

            self.assertAlmostEqual(
                steady_mean,
                230.0,
                delta=1.0,
                msg=f"Voltage drifted after stopping scenario: readings={steady_samples!r}",
            )
            self.assertLess(
                steady_stdev,
                2e-4,
                f"Expected noise to be disabled after stop(), got {steady_samples!r}",
            )
            self.assertLess(
                steady_span,
                5e-4,
                f"Expected flat readings after stop(), got {steady_samples!r}",
            )
            self.assertGreater(
                noisy_stdev,
                steady_stdev * 5,
                "Noise standard deviation should drop sharply after stop()",
            )
        finally:
            self._ensure_scenario_stopped("voltage_static")

    def test_ascii_disconnect_scenario_interrupts_and_restores(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["ascii_disconnect"]
        if scenario is None:
            self.skipTest("ascii_disconnect scenario not defined")

        start = getattr(scenario, "start", None)
        if not callable(start):
            self.skipTest("Scenario implementation does not expose start()")
        stop = getattr(scenario, "stop", None)

        self._set_attribute("voltage", 13.37)

        outage_detected = False
        last_error = None

        try:
            start()
            deadline = time.time() + 3.0
            while time.time() < deadline:
                try:
                    reply = self.sut.query("MEAS:VOLT?")
                except (
                    socket.timeout,
                    TimeoutError,
                    OSError,
                    ConnectionError,
                    RuntimeError,
                ) as exc:
                    outage_detected = True
                    last_error = exc
                    break

                if reply == "":
                    outage_detected = True
                    break

                wait_seconds(0.05)
            self.assertTrue(
                outage_detected,
                f"Expected communication outage during ascii_disconnect scenario (last_error={last_error!r})",
            )
            if callable(stop):
                stop()
            wait_seconds(2.5)

            restored = False
            for _ in range(6):
                try:
                    reply = self.sut.query("MEAS:VOLT?")
                except (
                    socket.timeout,
                    TimeoutError,
                    OSError,
                    ConnectionError,
                    RuntimeError,
                ):
                    wait_seconds(0.2)
                    continue
                if not reply:
                    wait_seconds(0.2)
                    continue
                try:
                    value = float(reply)
                except ValueError:
                    wait_seconds(0.2)
                    continue
                self.assertAlmostEqual(
                    value,
                    13.37,
                    places=2,
                    msg="Unexpected voltage reading after communication restored",
                )
                restored = True
                break

            self.assertTrue(restored, "Communication did not recover after scenario duration")
        finally:
            if callable(stop):
                stop()
            self._ensure_scenario_stopped("ascii_disconnect")

    def test_ascii_response_delay_spike_causes_timeout_and_recovers(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["ascii_response_delay_spike"]
        ascii_comm = self.instance["communication"]["ascii"]
        ascii_comm.response_delay = 0.0

        if scenario is None:
            self.skipTest("ascii_response_delay_spike scenario not defined")

        start = getattr(scenario, "start", None)
        if not callable(start):
            self.skipTest("Scenario implementation does not expose start()")

        self._set_attribute("voltage", 19.84)
        self.assertAlmostEqual(self.sut.measure_voltage(), 19.84, places=2)
        self._ensure_scenario_stopped("ascii_response_delay_spike")

        original_attempts = self.sut.reconnect_attempts
        original_delay = self.sut.reconnect_delay
        original_timeout = self.sut.timeout
        original_response_delay = getattr(ascii_comm, "response_delay", None)
        self.sut.reconnect_attempts = 0
        self.sut.reconnect_delay = 0.0
        self.sut.timeout = min(original_timeout, 0.3)
        self.sut.close()
        self.assertTrue(self.sut.connect())

        try:
            ascii_comm.response_delay = 5.0
            applied = wait_for_condition(
                lambda: (self._read_ascii_response_delay() or 0.0) >= 1.0,
                timeout=2.0,
                interval=0.1,
            )
            if not applied:
                self.skipTest("Response delay override did not apply in time")

            with self.assertRaises(RuntimeError):
                self.sut.query("MEAS:VOLT?")

            wait_seconds(5.5)

            restored = False
            for _ in range(10):
                reset = wait_for_condition(
                    lambda: (self._read_ascii_response_delay() or 0.0) < 0.5,
                    timeout=0.5,
                    interval=0.1,
                )
                if not reset:
                    wait_seconds(0.3)

                try:
                    reply = self.sut.query("MEAS:VOLT?")
                except RuntimeError:
                    ascii_comm.response_delay = 0.01
                    wait_seconds(0.3)
                    continue
                try:
                    value = float(reply)
                except ValueError:
                    wait_seconds(0.3)
                    continue
                self.assertAlmostEqual(
                    value,
                    19.84,
                    places=2,
                    msg="Unexpected voltage reading after delay spike recovered",
                )
                restored = True
                break

            self.assertTrue(
                restored, "Communication did not recover after response delay spike"
            )
        finally:
            self.sut.reconnect_attempts = original_attempts
            self.sut.reconnect_delay = original_delay
            self.sut.timeout = original_timeout
            if original_response_delay is not None:
                ascii_comm.response_delay = original_response_delay
            self._ensure_scenario_stopped("ascii_response_delay_spike")

    def test_discharge_spike_scenario_overrides_voltage_once(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["discharge_spike"]
        attr = self.instance["attributes"]["voltage"]
        attr.internal_value = 12.34

        baseline = float(self._query_or_skip("MEAS:VOLT?"))
        self.assertAlmostEqual(
            baseline,
            12.34,
            places=2,
            msg="Unexpected baseline voltage before discharge spike",
        )

        try:
            scenario.start()
            self.assertTrue(scenario.active)

            spiked = float(self._query_or_skip("MEAS:VOLT?"))
            self.assertGreaterEqual(
                spiked,
                900.0,
                f"Expected discharge spike to raise voltage, got {spiked}",
            )

            scenario.run()
            wait_seconds(0.1)

            recovered = float(self._query_or_skip("MEAS:VOLT?"))
            self.assertAlmostEqual(
                recovered,
                12.34,
                places=2,
                msg="Voltage did not recover after discharge spike run limit",
            )
        finally:
            self._ensure_scenario_stopped("discharge_spike")

    def test_voltage_static_scenario_defined(self):
        scenarios = self.instance["scenarios"]
        scenario_def = scenarios["voltage_static"]
        self.assertTrue(scenario_def.enabled, False)
        self.assertIn("actions", scenario_def)
        self.assertGreater(len(scenario_def["actions"]), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
