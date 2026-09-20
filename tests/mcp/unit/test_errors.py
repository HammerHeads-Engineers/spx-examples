# SPDX-License-Identifier: MIT

from spx_mcp.errors import (
    ModelValidationError,
    ProductKeyConfigError,
    WriteAccessError,
    exception_to_response,
)


def test_write_access_error_maps_to_structured_response() -> None:
    payload = exception_to_response(WriteAccessError("write disabled"))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "write_disabled"


def test_model_validation_error_includes_error_list() -> None:
    payload = exception_to_response(ModelValidationError(["one", "two"]))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "model_validation_failed"
    assert payload["error"]["details"]["errors"] == ["one", "two"]


def test_product_key_config_error_maps_to_structured_response() -> None:
    payload = exception_to_response(
        ProductKeyConfigError(
            "missing key",
            details={"status": "placeholder"},
        )
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "product_key_config_error"
    assert payload["error"]["details"]["status"] == "placeholder"
