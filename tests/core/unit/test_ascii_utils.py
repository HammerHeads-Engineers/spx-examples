# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest

from tests.common.ascii_utils import resolve_ascii_port, wait_for_ascii_port


def test_resolve_ascii_port_reads_from_attr_mapping() -> None:
    instance = {"communication": {"ascii": {"attr": {"port": {"value": 5026}}}}}

    port = resolve_ascii_port(instance)
    assert port == 5026


def test_resolve_ascii_port_reads_from_top_level_fields() -> None:
    instance = {"communication": {"ascii": {"port": "5030"}}}

    port = resolve_ascii_port(instance)
    assert port == 5030


def test_wait_for_ascii_port_times_out_when_missing() -> None:
    with pytest.raises(TimeoutError):
        wait_for_ascii_port({"communication": {}}, timeout=0.02, interval=0.0)


def test_wait_for_ascii_port_waits_until_available() -> None:
    class _Comm:
        def __init__(self) -> None:
            self._calls = 0

        @property
        def port(self):
            self._calls += 1
            return None if self._calls < 2 else 5045

    instance = {"communication": {"ascii": _Comm()}}

    port = wait_for_ascii_port(instance, timeout=0.2, interval=0.0)
    assert port == 5045
