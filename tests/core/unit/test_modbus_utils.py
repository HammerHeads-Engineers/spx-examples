# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest

from tests.common.modbus_utils import (
    resolve_modbus_endpoint,
    wait_for_modbus_endpoint,
)


def test_resolve_modbus_endpoint_reads_from_attr_mapping() -> None:
    instance = {
        "communication": {
            "modbus_slave": {
                "attr": {
                    "port": {"value": 5027},
                    "unit_id": {"value": 11},
                }
            }
        }
    }

    port, unit_id = resolve_modbus_endpoint(instance)
    assert port == 5027
    assert unit_id == 11


def test_resolve_modbus_endpoint_reads_from_top_level_fields() -> None:
    instance = {"communication": {"modbus_slave": {"port": "5028", "unit_id": 12}}}

    port, unit_id = resolve_modbus_endpoint(instance)
    assert port == 5028
    assert unit_id == 12


def test_resolve_modbus_endpoint_falls_back_to_id_field() -> None:
    instance = {"communication": {"modbus_slave": {"attr": {"port": {"value": 5030}, "id": {"value": 7}}}}}

    port, unit_id = resolve_modbus_endpoint(instance)
    assert port == 5030
    assert unit_id == 7


def test_wait_for_modbus_endpoint_times_out_when_missing() -> None:
    with pytest.raises(TimeoutError):
        wait_for_modbus_endpoint({"communication": {}}, timeout=0.02, interval=0.0)


def test_wait_for_modbus_endpoint_waits_until_available() -> None:
    class _Comm:
        def __init__(self) -> None:
            self._calls = 0

        @property
        def port(self):
            self._calls += 1
            return None if self._calls < 2 else 5040

        @property
        def unit_id(self):
            return 2

    instance = {"communication": {"modbus_slave": _Comm()}}

    port, unit_id = wait_for_modbus_endpoint(instance, timeout=0.2, interval=0.0)
    assert port == 5040
    assert unit_id == 2
