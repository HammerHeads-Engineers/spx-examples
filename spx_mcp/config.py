# SPDX-License-Identifier: MIT
"""Configuration helpers for the local SPX MCP tool."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Optional, Sequence, Tuple


MIN_MCP_PYTHON: Tuple[int, int] = (3, 10)
DEFAULT_SPX_BASE_URL = "http://localhost:8000"
PLACEHOLDER_PRODUCT_KEY_MARKERS = {
    "REPLACE_ME",
    "CHANGE_ME",
    "YOUR_PRODUCT_KEY",
    "YOUR_SPX_PRODUCT_KEY",
    "YOUR_KEY",
    "PRODUCT_KEY",
    "PLACEHOLDER",
}
WORKSPACE_MARKER_NAME = ".spx-mcp-workspace.json"
WORKSPACE_MARKER_KIND = "spx-codex-mcp-workspace"
WORKSPACE_KIND_MANAGED = "managed"
WORKSPACE_KIND_GIT = "git"
PRODUCT_KEY_MASK_RE = re.compile(r"[^A-Z0-9]+")


def normalize_base_url(value: str) -> str:
    """Return a canonical SPX base URL without a trailing slash."""
    return str(value or DEFAULT_SPX_BASE_URL).rstrip("/")


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
    product_key_source: Optional[str] = None
    product_key_status: str = "missing"
    product_key_search_details: Tuple[str, ...] = ()
    workspace_kind: Optional[str] = None
    default_work_mode: Optional[str] = None
    source_root: Optional[Path] = None

    @property
    def has_valid_product_key(self) -> bool:
        return self.product_key_status == "valid" and bool(self.product_key)

    def product_key_error_message(self) -> str:
        details = "; ".join(self.product_key_search_details) or "no search locations recorded"
        return (
            "SPX_PRODUCT_KEY is missing or invalid for this MCP workspace. "
            f"Search order: {details}"
        )

    def product_key_error_details(self) -> dict[str, object]:
        return {
            "status": self.product_key_status,
            "source": self.product_key_source,
            "search_order": list(self.product_key_search_details),
            "workspace_kind": self.workspace_kind,
            "default_work_mode": self.default_work_mode,
            "source_root": str(self.source_root) if self.source_root else None,
        }

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
        workspace_dotenv = _read_dotenv(root / ".env")
        marker = _read_workspace_marker(root)
        source_root = _marker_source_root(marker)
        source_dotenv = {}
        if _marker_workspace_kind(marker) == WORKSPACE_KIND_MANAGED and source_root is not None:
            source_dotenv = _read_dotenv(source_root / ".env")

        resolved_base_url = normalize_base_url(
            spx_base_url
            or os.environ.get("SPX_BASE_URL")
            or workspace_dotenv.get("SPX_BASE_URL")
            or DEFAULT_SPX_BASE_URL
        )
        resolved_product_key, product_key_source, product_key_status, search_details = _resolve_product_key(
            explicit=product_key,
            process_env=os.environ.get("SPX_PRODUCT_KEY"),
            workspace_env=workspace_dotenv.get("SPX_PRODUCT_KEY"),
            workspace_env_path=root / ".env",
            source_env=source_dotenv.get("SPX_PRODUCT_KEY"),
            source_env_path=(source_root / ".env") if source_root is not None else None,
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
            product_key_source=product_key_source,
            product_key_status=product_key_status,
            product_key_search_details=search_details,
            workspace_kind=_marker_workspace_kind(marker),
            default_work_mode=_marker_default_work_mode(marker),
            source_root=source_root,
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


def is_placeholder_product_key(value: Optional[str]) -> bool:
    normalized = _normalize_product_key_marker(value)
    return bool(normalized) and normalized in PLACEHOLDER_PRODUCT_KEY_MARKERS


def _normalize_product_key_marker(value: Optional[str]) -> str:
    if value is None:
        return ""
    raw = str(value).strip().upper()
    if not raw:
        return ""
    return PRODUCT_KEY_MASK_RE.sub("_", raw).strip("_")


def _classify_product_key(value: Optional[str]) -> str:
    if value is None:
        return "missing"
    stripped = str(value).strip()
    if not stripped:
        return "missing"
    if is_placeholder_product_key(stripped):
        return "placeholder"
    return "valid"


def _mask_product_key(value: Optional[str]) -> str:
    if value is None:
        return "not set"
    stripped = str(value).strip()
    if not stripped:
        return "empty"
    if is_placeholder_product_key(stripped):
        return f"placeholder {stripped}"
    if len(stripped) <= 6:
        return "<masked>"
    return f"{stripped[:3]}...{stripped[-2:]}"


def _format_candidate_detail(label: str, value: Optional[str]) -> str:
    status = _classify_product_key(value)
    if status == "valid":
        return f"{label}=valid {_mask_product_key(value)}"
    if status == "placeholder":
        return f"{label}=placeholder {_mask_product_key(value)}"
    return f"{label}=not set"


def _resolve_product_key(
    *,
    explicit: Optional[str],
    process_env: Optional[str],
    workspace_env: Optional[str],
    workspace_env_path: Path,
    source_env: Optional[str],
    source_env_path: Optional[Path],
) -> tuple[Optional[str], Optional[str], str, Tuple[str, ...]]:
    candidates = [
        ("explicit --product-key", explicit),
        ("process env SPX_PRODUCT_KEY", process_env),
        (f"workspace .env ({workspace_env_path})", workspace_env),
    ]
    if source_env_path is not None:
        candidates.append((f"managed source_root .env ({source_env_path})", source_env))

    search_details = tuple(
        _format_candidate_detail(label, value)
        for label, value in candidates
    )

    for label, value in candidates:
        if _classify_product_key(value) == "valid":
            return str(value).strip(), label, "valid", search_details

    if any(_classify_product_key(value) == "placeholder" for _, value in candidates):
        return None, None, "placeholder", search_details
    return None, None, "missing", search_details


def _read_workspace_marker(repo_root: Path) -> Optional[dict[str, object]]:
    marker_path = repo_root / WORKSPACE_MARKER_NAME
    if not marker_path.exists():
        return None
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") not in {None, WORKSPACE_MARKER_KIND}:
        return None
    return payload


def _marker_workspace_kind(marker: Optional[dict[str, object]]) -> Optional[str]:
    if not marker:
        return None
    workspace_kind = marker.get("workspace_kind")
    if isinstance(workspace_kind, str) and workspace_kind:
        return workspace_kind
    legacy_mode = marker.get("workspace_mode")
    if isinstance(legacy_mode, str) and legacy_mode:
        return legacy_mode
    return None


def _marker_default_work_mode(marker: Optional[dict[str, object]]) -> Optional[str]:
    if not marker:
        return None
    work_mode = marker.get("default_work_mode")
    if isinstance(work_mode, str) and work_mode:
        return work_mode
    workspace_kind = _marker_workspace_kind(marker)
    if workspace_kind == WORKSPACE_KIND_MANAGED:
        return "runtime_mcp"
    if workspace_kind == WORKSPACE_KIND_GIT:
        return "repo_dev"
    return None


def _marker_source_root(marker: Optional[dict[str, object]]) -> Optional[Path]:
    if not marker:
        return None
    raw_source_root = marker.get("source_root")
    if not isinstance(raw_source_root, str) or not raw_source_root:
        return None
    return Path(raw_source_root).expanduser().resolve()
