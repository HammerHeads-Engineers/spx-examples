# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared inline model stress test: start must clear measure_done on every fast cycle."""

import os
import unittest
import time

from tests.common.spx_utils import ensure_instance, ensure_model, wait_for_condition, wait_seconds

try:
    from modbus_tk import defines as cst  # type: ignore
    from modbus_tk import modbus_tcp  # type: ignore
    from modbus_tk.modbus import ModbusError  # type: ignore
except Exception:  # pragma: no cover - dependency missing
    cst = None  # type: ignore
    modbus_tcp = None  # type: ignore
    ModbusError = Exception  # type: ignore


MODEL_KEY = "tests__vacuum_gauge_done_reset_inline"
INSTANCE_KEY = "vacuum_gauge_done_reset_inline"
MODBUS_PORT = int(os.environ.get("SPX_VACUUM_GAUGE_PORT", "5025"))
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
DWELL_MS = 100
POLLING_INTERVAL = 0.001
STRESS_CYCLES = 1000


def _inline_model_def(modbus_port: int) -> dict:
    """Return the exact model definition used in the spx-server side test."""
    mapping = {
        "measure_done": {"address": [0, 0], "group": "h_r", "type": "uint_16"},
        "measure_start": {"address": [1, 1], "group": "h_r", "type": "uint_16"},
        "measure_config": {"address": [2, 2], "group": "h_r", "type": "uint_16"},
        "dwell_time": {"address": [3, 3], "group": "h_r", "type": "uint_16"},
        "ch_1_impulse": {"address": [4, 5], "group": "h_r", "type": "uint_32"},
        "ch_2_impulse": {"address": [6, 7], "group": "h_r", "type": "uint_32"},
        "ch_3_impulse": {"address": [8, 9], "group": "h_r", "type": "uint_32"},
        "ch_4_impulse": {"address": [10, 11], "group": "h_r", "type": "uint_32"},
        "ch_5_impulse": {"address": [12, 13], "group": "h_r", "type": "uint_32"},
        "ch_6_impulse": {"address": [14, 15], "group": "h_r", "type": "uint_32"},
        "ch_7_impulse": {"address": [16, 17], "group": "h_r", "type": "uint_32"},
        "ch_1_comparator": {"address": [18, 18], "group": "h_r", "type": "uint_16"},
        "ch_2_comparator": {"address": [19, 19], "group": "h_r", "type": "uint_16"},
        "ch_3_comparator": {"address": [20, 20], "group": "h_r", "type": "uint_16"},
        "ch_4_comparator": {"address": [21, 21], "group": "h_r", "type": "uint_16"},
        "ch_5_comparator": {"address": [22, 22], "group": "h_r", "type": "uint_16"},
        "ch_6_comparator": {"address": [23, 23], "group": "h_r", "type": "uint_16"},
        "ch_7_comparator": {"address": [24, 24], "group": "h_r", "type": "uint_16"},
    }

    return {
        "attributes": {
            "measure_done": {"type": "int", "default": 1},
            "measure_start": {
                "type": "int",
                "default": 0,
                "hooks": {"on_set": ["refresh_model"]},
            },
            "measure_config": 0,
            "dwell_time": DWELL_MS,
            "ch_1_impulse": 0,
            "ch_2_impulse": 0,
            "ch_3_impulse": 0,
            "ch_4_impulse": 0,
            "ch_5_impulse": 0,
            "ch_6_impulse": 0,
            "ch_7_impulse": 0,
            "ch_1_comparator": 0,
            "ch_2_comparator": 0,
            "ch_3_comparator": 0,
            "ch_4_comparator": 0,
            "ch_5_comparator": 0,
            "ch_6_comparator": 0,
            "ch_7_comparator": 0,
            "_start_ms": 0,
            "auto_trigger_enable": 0,
            "_counter_start": 0,
            "_counter_done": 0,
        },
        "conditions": [
            {
                "if": "$in(measure_start) == 1",
                "actions": [
                    {
                        "function": "$in(_start_ms)",
                        "imports": ["time"],
                        "call": "time.monotonic()*1000",
                    },
                    {"set": "$in(measure_done)", "value": 0},
                    {"set": "$in(measure_start)", "value": 0},
                    {
                        "function": "$in(_counter_start)",
                        "call": "$in(_counter_start) + 1",
                    },
                ],
            },
            {
                "if": "$in(measure_done) == 0",
                "actions": [
                    {
                        "function": "$in(measure_done)",
                        "imports": ["time"],
                        "call": (
                            "0 if (time.monotonic()*1000 - $in(_start_ms) < $in(dwell_time)) "
                            "else 1"
                        ),
                    },
                    {
                        "function": "$in(_counter_done)",
                        "call": "($in(_counter_done) + 1) if $in(measure_done)==1 else $in(_counter_done)",
                    },
                ],
            },
        ],

            # {
            #     "function": "$in(ch_1_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_1_comparator)",
            #         "seed": 101,
            #         "base_min": 5.0,
            #         "base_max": 15.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_1_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_2_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_2_comparator)",
            #         "seed": 203,
            #         "base_min": 3.0,
            #         "base_max": 12.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_2_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_3_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_3_comparator)",
            #         "seed": 307,
            #         "base_min": 8.0,
            #         "base_max": 25.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_3_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_4_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_4_comparator)",
            #         "seed": 409,
            #         "base_min": 15.0,
            #         "base_max": 40.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_4_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_5_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_5_comparator)",
            #         "seed": 503,
            #         "base_min": 5.0,
            #         "base_max": 15.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_5_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_6_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_6_comparator)",
            #         "seed": 601,
            #         "base_min": 5.0,
            #         "base_max": 15.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_6_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },
            # {
            #     "function": "$in(ch_7_impulse)",
            #     "imports": ["random"],
            #     "params": {
            #         "comparator": "$in(ch_7_comparator)",
            #         "seed": 709,
            #         "base_min": 5.0,
            #         "base_max": 15.0,
            #         "dt": "$(~.polling.interval) or 0.01",
            #     },
            #     "call": (
            #         "(\n"
            #         "  $in(ch_7_impulse) if ($in(measure_start)==1 or $in(_measuring_active)==1 or $in(_start_ms)==0) else\n"
            #         "  int(random.Random(int($in(_start_ms)) + seed).uniform(base_min, base_max)\n"
            #         "      * max(1, int(max(1.0, $in(dwell_time)) / (dt * 1000.0)))\n"
            #         "      / (1.0 + max(0, comparator) / 50.0))\n"
            #         ")"
            #     ),
            # },

        "polling": {"interval": POLLING_INTERVAL},
        "communication": [
            {
                "modbus_slave": {
                    "host": "0.0.0.0",
                    "unit_id": 1,
                    "port": modbus_port,
                    "zero_fill": True,
                    "mapping": mapping,
                }
            }
        ],
    }


class TestModbusVacuumGaugeDoneResetInlineModel(unittest.TestCase):
    """Exact inline model recreation to isolate done-reset behaviour."""

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        if modbus_tcp is None or cst is None:
            raise unittest.SkipTest("modbus_tk is not available")

        cls._spx = spx_python
        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest(
                "SPX_PRODUCT_KEY must be set to run integration tests."
            )

        client = spx_python.init(address=SPX_API_URL, product_key=product_key)
        model_def = _inline_model_def(MODBUS_PORT)

        ensure_model(client, MODEL_KEY, model_def)
        cls._instance = ensure_instance(
            client,
            INSTANCE_KEY,
            MODEL_KEY,
            recreate=True,  # force fresh instance to match inline model
            ensure_running=True,
            reset_on_create=True,
            start_on_create=True,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.2)

        self.master = modbus_tcp.TcpMaster(host="127.0.0.1", port=MODBUS_PORT)
        self.master.set_timeout(1.0)
        # modbus_tk TcpMaster connects lazily on first execute
        try:
            state = (self.model.get() or {}).get("state")
        except Exception:
            state = None
        if state not in {"running", "RUNNING"}:
            try:
                self.model.start()
            except Exception:
                pass
            wait_for_condition(
                lambda: str((self.model.get() or {}).get("state")).lower() == "running",
                timeout=2.0,
                interval=0.05,
            )

    def tearDown(self):
        if hasattr(self, "master") and self.master:
            try:
                self.master.close()
            except Exception:
                pass

    def test_start_clears_done_and_recovers_every_cycle(self):
        """Cycle 1000x with dwell=20ms using the inline model definition."""

        def _read_reg(addr: int) -> int:
            return int(self.master.execute(1, cst.READ_HOLDING_REGISTERS, addr, 1)[0])

        def _write_reg(addr: int, value: int) -> None:
            try:
                self.master.execute(1, cst.WRITE_SINGLE_REGISTER, addr, output_value=int(value) & 0xFFFF)
            except ModbusError as exc:  # pragma: no cover - defensive logging
                raise AssertionError(f"Modbus write failed at addr {addr} value {value}: {exc}") from exc

        # # Baseline state for each run.
        # _write_reg(1, 0)  # measure_start
        # _write_reg(0, 1)  # measure_done
        # _write_reg(3, DWELL_MS)  # dwell_time

        # self.assertTrue(
        #     wait_for_condition(lambda: _read_reg(0) == 1, timeout=2.0, interval=0.01),
        #     "Expected measure_done to be 1 before starting cycles",
        # )

        attrs = self.model["attributes"]
        attr_start = attrs["measure_start"]
        attr_done = attrs["measure_done"]
        binds = self.model["communication"]["modbus_slave"]["bindings"]
        print(f"Attribute bindings: {binds.keys()}")
        bind_done = binds["binding_0"]
        bind_start = binds["binding_1"]
        print(f"History of communication bindings: {bind_done.tail()}", )
        counter_start = attrs["_counter_start"]
        counter_done = attrs["_counter_done"]
        timings_ms = []
        cycle_ms = []

        for cycle in range(STRESS_CYCLES):
            # # force edge on measure_start to guarantee on_set runs each cycle
            # _write_reg(1, 0)
            # wait_for_condition(lambda: _read_reg(1) == 0, timeout=0.05, interval=0.001)

            t0 = time.perf_counter()
            _write_reg(1, 1)
            #wait_seconds(0.0)  # allow on_set to process
            done_after_start = _read_reg(0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            timings_ms.append(elapsed_ms)

            # self.assertEqual(
            #     start_reg,
            #     0,
            #     f"Cycle {cycle + 1}: measure_start register should read 0 after write; got {start_reg}",
            # )

            self.assertEqual(
                done_after_start,
                0,
                f"Cycle {cycle + 1}: measure_done register should read 0 immediately after start; got {done_after_start}"
                f" attr_start={attr_start.internal_value}, attr_done={attr_done.internal_value},"
                f" counter_start={counter_start.internal_value}, counter_done={counter_done.internal_value}"
            )

            # self.assertTrue(
            #     wait_for_condition(lambda: _read_reg(0) == 0, timeout=0.05, interval=0.001),
            #     (
            #         f"Cycle {cycle + 1}: measure_done should clear to 0 after start; "
            #         f"start_reg={start_reg}, attr_start={attr_start_val}, attr_done={attr_done_val}"
            #     ),
            # )
            # self.assertTrue(
            #     wait_for_condition(lambda: _read_reg(1) == 0, timeout=0.05, interval=0.001),
            #     f"Cycle {cycle + 1}: measure_start should auto-reset to 0",
            # )
            # attr_start.internal_value = 0  # simulate on_set effect
            self.assertTrue(
                wait_for_condition(lambda: _read_reg(0) == 1, timeout=0.50, interval=0.002),
                f"Cycle {cycle + 1}: measure_done should return to 1 after dwell completes",
            )
            cycle_ms.append((time.perf_counter() - t0) * 1000.0)

        if timings_ms:
            avg_ms = sum(timings_ms) / len(timings_ms)
            min_ms = min(timings_ms)
            max_ms = max(timings_ms)
            sorted_ms = sorted(timings_ms)
            mid = len(sorted_ms) // 2
            median_ms = (
                (sorted_ms[mid - 1] + sorted_ms[mid]) / 2.0
                if len(sorted_ms) % 2 == 0
                else sorted_ms[mid]
            )
            avg_cycle = sum(cycle_ms) / len(cycle_ms) if cycle_ms else 0.0
            print(
                f"Timing summary over {len(timings_ms)} cycles: "
                f"avg={avg_ms:.2f} ms, median={median_ms:.2f} ms, "
                f"min={min_ms:.2f} ms, max={max_ms:.2f} ms; "
                f"cycle avg start->done=1 = {avg_cycle:.2f} ms"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
