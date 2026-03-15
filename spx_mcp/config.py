# SPDX-License-Identifier: MIT
"""Configuration helpers for the local SPX MCP tool."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple


MIN_MCP_PYTHON: Tuple[int, int] = (3, 10)


def normalize_base_url(value: str) -> str:
    """Return a canonical SPX base URL without a trailing slash."""
    return str(value or "http://localhost:8000").rstrip("/")


def python_supports_mcp(
    version_info: Optional[Sequence[int]] = None,
) -> bool:
    """Return True when the runtime satisfies the MCP SDK minimum Python version."""
    parts = tuple(version_info or sys.version_info)
    return parts[:2] >= MIN_MCP_PYTHON


def runtime_requirement_message() -> str:
    """Human-readable runtime requirements for the MCP CLI."""
    return (
        "The local MCP tool requires Python "
        f"{MIN_MCP_PYTHON[0]}.{MIN_MCP_PYTHON[1]}+ and the optional 'mcp' package."
    )


@dataclass(frozen=True)
class SpxMcpConfig:
    """Runtime configuration for the local MCP server."""

    repo_root: Path
    spx_base_url: str
    product_key: Optional[str]
    allow_write: bool = False
    pretty_errors: bool = True
    fault_verbose: bool = False

    @classmethod
    def from_sources(
        cls,
        *,
        repo_root: Optional[str] = None,
        spx_base_url: Optional[str] = None,
        product_key: Optional[str] = None,
        allow_write: bool = False,
        pretty_errors: Optional[bool] = None,
        fault_verbose: Optional[bool] = None,
    ) -> "SpxMcpConfig":
        root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
        dotenv = _read_dotenv(root / ".env")
        resolved_base_url = normalize_base_url(
            spx_base_url
            or os.environ.get("SPX_BASE_URL")
            or dotenv.get("SPX_BASE_URL", "http://localhost:8000")
        )
        resolved_product_key = (
            product_key
            if product_key is not None
            else os.environ.get("SPX_PRODUCT_KEY") or dotenv.get("SPX_PRODUCT_KEY")
        )
        resolved_pretty = pretty_errors
        if resolved_pretty is None:
            resolved_pretty = _env_flag("SPX_PRETTY_ERRORS", default=True)
        resolved_fault_verbose = fault_verbose
        if resolved_fault_verbose is None:
            resolved_fault_verbose = _env_flag(
                "SPX_CLIENT_FAULT_VERBOSE",
                default=False,
            )
        return cls(
            repo_root=root,
            spx_base_url=resolved_base_url,
            product_key=resolved_product_key,
            allow_write=allow_write,
            pretty_errors=bool(resolved_pretty),
            fault_verbose=bool(resolved_fault_verbose),
        )


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value

    return values
