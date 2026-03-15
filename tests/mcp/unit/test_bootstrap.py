# SPDX-License-Identifier: MIT

import pytest

from spx_mcp.backend.bootstrap import meta_parameter_defaults


def test_meta_parameter_defaults_uses_defaults_and_overrides() -> None:
    payload = {
        "meta_parameters": {
            "port": {"type": "int", "default": 5020},
            "zone": {"type": "str", "required": True},
        }
    }

    params, missing = meta_parameter_defaults(payload, overrides={"zone": "north"})

    assert params["port"] == {"cycle": [5020]}
    assert params["zone"] == {"cycle": ["north"]}
    assert missing == []


def test_meta_parameter_defaults_rejects_unknown_overrides() -> None:
    payload = {"meta_parameters": {"port": {"type": "int", "default": 1}}}

    with pytest.raises(ValueError):
        meta_parameter_defaults(payload, overrides={"missing": 2})
