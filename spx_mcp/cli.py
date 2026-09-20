# SPDX-License-Identifier: MIT
"""CLI for the local SPX MCP server."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
import sys
from typing import Iterable, Optional

from .config import MIN_MCP_PYTHON, SpxMcpConfig, python_supports_mcp, runtime_requirement_message
from .toolsets import get_tool_specs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spx-mcp",
        description="Local MCP tool for the spx-examples repository.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    stdio_parser = subparsers.add_parser("stdio", help="Run the MCP server over stdio.")
    _add_common_runtime_args(stdio_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Print environment diagnostics for the local MCP tool.",
    )
    _add_common_runtime_args(doctor_parser)
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit diagnostics as JSON.",
    )

    list_parser = subparsers.add_parser(
        "list-tools",
        help="List MCP tools exposed by the local server.",
    )
    list_parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Include write tools in the static list.",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the tool list as JSON.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "stdio":
        config = _config_from_args(args)
        try:
            from .server import build_server

            build_server(config).run(transport="stdio")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "doctor":
        config = _config_from_args(args)
        report = doctor_report(config)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_doctor_report(report)
        return 0 if report["ok"] else 1

    if args.command == "list-tools":
        specs = get_tool_specs(allow_write=bool(args.allow_write))
        if args.json:
            print(json.dumps(specs, indent=2, sort_keys=True))
        else:
            for spec in specs:
                mode = "write" if spec.get("write") else "read"
                print(f"{spec['name']} [{mode}] - {spec['description']}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def doctor_report(config: SpxMcpConfig):
    """Return a structured diagnostics report for the local MCP runtime."""
    problems = []
    if not python_supports_mcp():
        problems.append(runtime_requirement_message())
    if not config.has_valid_product_key:
        problems.append(config.product_key_error_message())
    if not (config.repo_root / "library" / "catalog" / "models.yaml").exists():
        problems.append("Repository catalog file library/catalog/models.yaml is missing.")

    mcp_available = find_spec("mcp") is not None
    if not mcp_available:
        problems.append(
            "Optional dependency 'mcp' is unavailable. "
            f"Use Python {MIN_MCP_PYTHON[0]}.{MIN_MCP_PYTHON[1]}+ and install project dependencies there."
        )
    runtime_backend = runtime_backend_report()
    if not runtime_backend["spx_python_available"]:
        problems.append(
            "Dependency 'spx-python' is unavailable. "
            "Install project dependencies with 'poetry install --with dev'."
        )
    problems.extend(runtime_backend["problems"])

    return {
        "ok": not problems,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "repo_root": str(config.repo_root),
        "spx_base_url": config.spx_base_url,
        "product_key_present": bool(config.has_valid_product_key),
        "product_key_status": config.product_key_status,
        "product_key_source": config.product_key_source,
        "allow_write": config.allow_write,
        "mcp_sdk_available": mcp_available,
        "spx_python_available": runtime_backend["spx_python_available"],
        "spx_python_importable": runtime_backend["spx_python_importable"],
        "runtime_backend_usable": runtime_backend["ok"],
        "runtime_backend_checks": runtime_backend["checks"],
        "problems": problems,
    }


def _print_doctor_report(report) -> None:
    print(f"python_version: {report['python_version']}")
    print(f"repo_root: {report['repo_root']}")
    print(f"spx_base_url: {report['spx_base_url']}")
    print(f"product_key_present: {report['product_key_present']}")
    print(f"product_key_status: {report['product_key_status']}")
    print(f"product_key_source: {report['product_key_source']}")
    print(f"allow_write: {report['allow_write']}")
    print(f"mcp_sdk_available: {report['mcp_sdk_available']}")
    print(f"spx_python_available: {report['spx_python_available']}")
    print(f"spx_python_importable: {report['spx_python_importable']}")
    print(f"runtime_backend_usable: {report['runtime_backend_usable']}")
    print("runtime_backend_checks:")
    for check in report["runtime_backend_checks"]:
        print(f"- {check}")
    if report["problems"]:
        print("problems:")
        for problem in report["problems"]:
            print(f"- {problem}")
    else:
        print("problems: none")


def _add_common_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root (defaults to the current project root).",
    )
    parser.add_argument(
        "--spx-base-url",
        default=None,
        help="SPX server base URL (defaults to SPX_BASE_URL or http://localhost:8000).",
    )
    parser.add_argument(
        "--product-key",
        default=None,
        help="SPX product key (defaults to SPX_PRODUCT_KEY).",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Expose write tools in addition to read-only and diagnostics tools.",
    )


def _config_from_args(args: argparse.Namespace) -> SpxMcpConfig:
    return SpxMcpConfig.from_sources(
        repo_root=getattr(args, "repo_root", None),
        spx_base_url=getattr(args, "spx_base_url", None),
        product_key=getattr(args, "product_key", None),
        allow_write=bool(getattr(args, "allow_write", False)),
    )


def runtime_backend_report() -> dict[str, object]:
    """Return diagnostics for the actual runtime bootstrap path used by MCP."""
    checks: list[str] = []
    problems: list[str] = []
    spx_python_available = find_spec("spx_python") is not None
    spx_python_importable = False

    if spx_python_available:
        try:
            import spx_python  # noqa: F401
            from spx_python.client import SpxClient  # noqa: F401

            spx_python_importable = True
            checks.append("spx_python and spx_python.client import successfully")
        except Exception as exc:
            problems.append(
                "Dependency 'spx-python' is present but failed to import: "
                f"{type(exc).__name__}: {exc}"
            )

    try:
        from spx_mcp.backend.bootstrap import runtime_bootstrap_backend_report
        from spx_mcp.backend.models import runtime_model_backend_report

        model_report = runtime_model_backend_report()
        bootstrap_report = runtime_bootstrap_backend_report()
        checks.extend(model_report.get("checks", []))
        checks.extend(bootstrap_report.get("checks", []))
    except Exception as exc:
        problems.append(
            "The MCP runtime bootstrap path is not importable: "
            f"{type(exc).__name__}: {exc}"
        )

    return {
        "ok": not problems,
        "checks": checks,
        "problems": problems,
        "spx_python_available": spx_python_available,
        "spx_python_importable": spx_python_importable,
    }
