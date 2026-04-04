# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path
from typing import Optional

from tests.common.repo import repo_root
from tests.common.spx_utils import (
    ensure_instance,
    ensure_model,
    load_model_definition,
    wait_for_condition,
)


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")

PLC_MODEL_ID = "Industrial.PlcController.ModbusMaster"
PLC_INSTANCE_KEY = "spx_plc_controller_modbus_master_demo"
DRIVE_MODEL_ID = "Motion.VFDrive.SchneiderAltivar320.Modbus"
DRIVE_INSTANCE_KEY = "spx_altivar_320_vfd_plc_demo"
METER_MODEL_ID = "Energy.EnergyMeterIem3000.Modbus"
METER_INSTANCE_KEY = "spx_iem3000_meter_plc_demo"


def _pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _instance_state(instance) -> Optional[str]:
    try:
        state = instance.state
    except Exception:
        state = None
    if isinstance(state, str):
        return state

    try:
        doc = instance.get()
    except Exception:
        doc = None
    if isinstance(doc, dict):
        value = doc.get("state")
        if isinstance(value, str):
            return value
        attr = doc.get("attr")
        if isinstance(attr, dict):
            state_attr = attr.get("state")
            if isinstance(state_attr, dict):
                state_value = state_attr.get("value")
                if isinstance(state_value, str):
                    return state_value
    return None


def _float_attr(attr) -> Optional[float]:
    try:
        value = attr.internal_value
    except Exception:
        value = None
    if value is None:
        value = attr
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_attr(attr) -> Optional[int]:
    value = _float_attr(attr)
    if value is None:
        return None
    return int(round(value))


class TestModbusMasterPlcDemoSmokeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        root = repo_root()

        cls._plc_def = load_model_definition(
            Path(root / "library/domains/industrial/controller/generic/plc_controller__modbus_master.yaml")
        )
        cls._drive_def = load_model_definition(
            Path(root / "library/domains/industrial/drive/schneider/schneider_altivar_320__modbus.yaml")
        )
        cls._meter_def = load_model_definition(
            Path(root / "library/domains/energy/meter/schneider/energy_meter_iem3000__modbus.yaml")
        )

        ensure_model(cls._client, PLC_MODEL_ID, cls._plc_def)
        ensure_model(cls._client, DRIVE_MODEL_ID, cls._drive_def)
        ensure_model(cls._client, METER_MODEL_ID, cls._meter_def)

        cls._drive_port = _pick_free_port()
        cls._meter_port = _pick_free_port()
        cls._drive_unit_id = 11
        cls._meter_unit_id = 21

        cls._drive = ensure_instance(
            cls._client,
            DRIVE_INSTANCE_KEY,
            DRIVE_MODEL_ID,
            model_def=cls._drive_def,
            meta_parameters={
                "modbus_port": cls._drive_port,
                "modbus_unit_id": cls._drive_unit_id,
            },
            recreate=True,
            ensure_running=True,
        )
        cls._meter = ensure_instance(
            cls._client,
            METER_INSTANCE_KEY,
            METER_MODEL_ID,
            model_def=cls._meter_def,
            meta_parameters={
                "modbus_port": cls._meter_port,
                "modbus_unit_id": cls._meter_unit_id,
            },
            recreate=True,
            ensure_running=True,
        )
        cls._plc = ensure_instance(
            cls._client,
            PLC_INSTANCE_KEY,
            PLC_MODEL_ID,
            model_def=cls._plc_def,
            meta_parameters={
                "drive_host": "127.0.0.1",
                "drive_port": cls._drive_port,
                "drive_unit_id": cls._drive_unit_id,
                "meter_host": "127.0.0.1",
                "meter_port": cls._meter_port,
                "meter_unit_id": cls._meter_unit_id,
            },
            recreate=True,
            ensure_running=True,
        )

        for instance in (cls._drive, cls._meter, cls._plc):
            ready = wait_for_condition(
                lambda inst=instance: (_instance_state(inst) or "").lower() == "running",
                timeout=10.0,
                interval=0.2,
            )
            if not ready:
                raise AssertionError(f"Instance did not reach RUNNING: {instance}")

    @classmethod
    def tearDownClass(cls):
        for key in (PLC_INSTANCE_KEY, DRIVE_INSTANCE_KEY, METER_INSTANCE_KEY):
            try:
                instance = cls._client["instances"][key]
            except Exception:
                instance = None
            if instance is None:
                continue
            try:
                instance.stop()
            except Exception:
                pass
            try:
                del cls._client["instances"][key]
            except Exception:
                pass

    def test_master_reads_drive_and_meter_feedback(self):
        plc_attrs = self._plc["attributes"]

        meter_ready = wait_for_condition(
            lambda: (_float_attr(plc_attrs["meter_active_power_total_kw"]) or 0.0) > 1.0,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(meter_ready, "PLC did not read active power from the iEM3000 meter.")

        frequency_ready = wait_for_condition(
            lambda: abs((_float_attr(plc_attrs["meter_frequency_hz"]) or 0.0) - 50.0) <= 1.0,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(frequency_ready, "PLC did not read frequency from the iEM3000 meter.")

        drive_status_ready = wait_for_condition(
            lambda: (_int_attr(plc_attrs["drive_status_word_raw"]) or 0) >= 1,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(drive_status_ready, "PLC did not read the Altivar status word.")

    def test_master_controls_drive_and_enforces_power_limit(self):
        plc_attrs = self._plc["attributes"]
        drive_attrs = self._drive["attributes"]

        plc_attrs["k__power_limit_kw"].internal_value = 20.0
        plc_attrs["k__drive_speed_setpoint_hz"].internal_value = 24.0
        plc_attrs["k__drive_run_enable"].internal_value = 1

        drive_run_written = wait_for_condition(
            lambda: (_int_attr(drive_attrs["cmd__control_word_raw"]) or 0) == 1,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(drive_run_written, "PLC did not write the Altivar run command.")

        drive_speed_written = wait_for_condition(
            lambda: (_int_attr(drive_attrs["k__speed_setpoint_raw"]) or -1) == 24,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(drive_speed_written, "PLC did not write the Altivar speed reference.")

        drive_feedback_ready = wait_for_condition(
            lambda: (_float_attr(plc_attrs["drive_speed_actual_hz"]) or 0.0) > 0.5,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(drive_feedback_ready, "PLC did not read the Altivar speed feedback.")

        plc_attrs["k__power_limit_kw"].internal_value = 3.0

        limit_active = wait_for_condition(
            lambda: (_int_attr(plc_attrs["power_limit_active"]) or 0) == 1,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(limit_active, "PLC power-limit interlock did not activate.")

        drive_stopped = wait_for_condition(
            lambda: _int_attr(drive_attrs["cmd__control_word_raw"]) == 0,
            timeout=10.0,
            interval=0.2,
        )
        self.assertTrue(drive_stopped, "PLC did not clear the Altivar run command on power limit.")
