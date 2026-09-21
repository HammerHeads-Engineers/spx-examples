# SPDX-License-Identifier: MIT
"""Error types and response mapping for MCP tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


class WriteAccessError(RuntimeError):
    """Raised when a write tool is used without explicit write enablement."""


@dataclass
class ProductKeyConfigError(RuntimeError):
    """Raised when the MCP runtime cannot resolve a usable SPX product key."""

    message: str
    details: Dict[str, Any]

    def __str__(self) -> str:
        return self.message


@dataclass
class ModelValidationError(RuntimeError):
    """Raised when a model fails local repository validation."""

    errors: Iterable[str]

    def __str__(self) -> str:
        return "Model validation failed"


def success_response(**payload: Any) -> Dict[str, Any]:
    """Build a normalized success payload for MCP tools."""
    result: Dict[str, Any] = {"ok": True}
    result.update(payload)
    return result


def error_response(
    message: str,
    *,
    code: str = "error",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a normalized error payload for MCP tools."""
    result: Dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        result["error"]["details"] = details
    return result


def exception_to_response(exc: Exception) -> Dict[str, Any]:
    """Map known exception types into a structured MCP tool error payload."""
    if isinstance(exc, WriteAccessError):
        return error_response(str(exc), code="write_disabled")

    if isinstance(exc, ProductKeyConfigError):
        return error_response(
            str(exc),
            code="product_key_config_error",
            details=dict(exc.details),
        )

    if isinstance(exc, ModelValidationError):
        return error_response(
            str(exc),
            code="model_validation_failed",
            details={"errors": list(exc.errors)},
        )

    fault = getattr(exc, "fault", None)
    if fault is not None:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        correlation_id = getattr(exc, "correlation_id", None)
        details: Dict[str, Any] = {
            "fault": fault,
        }
        if status_code is not None:
            details["http_status"] = status_code
        if correlation_id:
            details["correlation_id"] = correlation_id
        return error_response(str(exc), code="spx_api_error", details=details)

    return error_response(str(exc), code="runtime_error")
