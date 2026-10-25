#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Live stdio smoke test for the local SPX MCP tool."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from spx_mcp.config import SpxMcpConfig


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ID = "Env.AirQualityStation.Http"
DEFAULT_INSTANCE_KEY = "mcp_smoke_air_quality"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live stdio smoke test against the local spx_mcp server.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to launch the MCP server subprocess.",
    )
    parser.add_argument(
        "--spx-base-url",
        default=os.environ.get("SPX_BASE_URL", "http://localhost:8000"),
        help="SPX base URL used by the MCP server.",
    )
    parser.add_argument(
        "--product-key",
        default=None,
        help="SPX product key. Defaults to .env or SPX_PRODUCT_KEY.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="Catalog model id used for the write-enabled smoke flow.",
    )
    parser.add_argument(
        "--instance-key",
        default=DEFAULT_INSTANCE_KEY,
        help="Instance key used for the write-enabled smoke flow.",
    )
    return parser


def load_product_key(explicit: Optional[str]) -> str:
    config = SpxMcpConfig.from_sources(
        repo_root=str(ROOT),
        product_key=explicit,
    )
    if config.has_valid_product_key and config.product_key:
        return config.product_key
    raise SystemExit(config.product_key_error_message())


def server_command_args(
    *,
    repo_root: Path,
    spx_base_url: str,
    product_key: str,
) -> List[str]:
    return [
        "-m",
        "spx_mcp",
        "stdio",
        "--allow-write",
        "--repo-root",
        str(repo_root),
        "--spx-base-url",
        spx_base_url,
        "--product-key",
        product_key,
    ]


def summarize_result(result) -> Dict[str, Any]:
    structured = unwrap_structured(result)
    payload: Dict[str, Any] = {
        "transport_error": bool(getattr(result, "isError", False)),
        "structured": structured,
    }
    text_blocks: List[str] = []
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if text is not None:
            text_blocks.append(text)
    if text_blocks:
        payload["content"] = text_blocks
    return payload


def is_success(result) -> bool:
    if getattr(result, "isError", False):
        return False
    structured = unwrap_structured(result)
    if isinstance(structured, dict):
        return bool(structured.get("ok", False))
    return True


def unwrap_structured(result) -> Any:
    structured = getattr(result, "structuredContent", None)
    if (
        isinstance(structured, dict)
        and set(structured.keys()) == {"result"}
        and isinstance(structured["result"], dict)
    ):
        return structured["result"]
    return structured


async def run_smoke(
    python_executable: str,
    spx_base_url: str,
    product_key: str,
    model_id: str,
    instance_key: str,
) -> int:
    params = StdioServerParameters(
        command=python_executable,
        args=server_command_args(
            repo_root=ROOT,
            spx_base_url=spx_base_url,
            product_key=product_key,
        ),
        cwd=ROOT,
        env=dict(os.environ),
    )

    steps: Iterable[Tuple[str, Dict[str, Any]]] = [
        ("health", {}),
        ("repo_validate_model", {"model_id": model_id}),
        ("server_register_model_from_catalog", {"model_id": model_id}),
        ("server_list_models", {}),
        (
            "server_ensure_instance",
            {
                "model_id": model_id,
                "instance_key": instance_key,
                "start": True,
                "recreate": True,
            },
        ),
        ("server_get_instance", {"instance_key": instance_key}),
        ("server_list_scenarios", {"instance_key": instance_key}),
        ("server_get_logs", {"instance_key": instance_key}),
        ("server_get_communication", {"instance_key": instance_key}),
        ("server_diagnose_instance", {"instance_key": instance_key}),
    ]
    scenario_name = "mcp_smoke_runtime_action"
    scenario_payload = {
        "description": "Temporary runtime-injected action scenario used by the MCP smoke test.",
        "duration": 0.8,
        "period": 0.1,
        "actions": [
            {
                "function": "$in(k__current_pm2_5)",
                "params": {
                    "low": 9.9,
                    "high": 19.9,
                    "switch_at": 0.25,
                },
                "call": "low if $attr(timer.time) < switch_at else high",
            }
        ],
    }

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            print(f"initialized: {init.serverInfo.name} {init.serverInfo.version}")

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print(f"tool_count: {len(tool_names)}")
            print(
                "write_tools_enabled:",
                "server_register_model_from_catalog" in tool_names,
            )

            for name, arguments in steps:
                result = await session.call_tool(name, arguments)
                summary = summarize_result(result)
                print(f"\n[{name}]")
                print(summary)
                if not is_success(result):
                    print(f"step_failed: {name}")
                    return 1

            scenario_result = await session.call_tool(
                "server_upsert_scenario",
                {
                    "instance_key": instance_key,
                    "scenario_name": scenario_name,
                    "scenario": scenario_payload,
                },
            )
            print("\n[server_upsert_scenario]")
            print(summarize_result(scenario_result))
            if not is_success(scenario_result):
                print("step_failed: server_upsert_scenario")
                return 1

            get_result = await session.call_tool(
                "server_get_scenario",
                {
                    "instance_key": instance_key,
                    "scenario_name": scenario_name,
                },
            )
            print("\n[server_get_scenario]")
            print(summarize_result(get_result))
            if not is_success(get_result):
                print("step_failed: server_get_scenario")
                return 1

            start_result = await session.call_tool(
                "server_start_scenario",
                {
                    "instance_key": instance_key,
                    "scenario_name": scenario_name,
                },
            )
            print("\n[server_start_scenario]")
            print(summarize_result(start_result))
            if not is_success(start_result):
                print("step_failed: server_start_scenario")
                return 1

            await anyio.sleep(0.45)

            attr_result = await session.call_tool(
                "server_get_attr",
                {
                    "instance_key": instance_key,
                    "attr_path": "attributes/k__current_pm2_5",
                },
            )
            attr_summary = summarize_result(attr_result)
            print("\n[server_get_attr after scenario]")
            print(attr_summary)
            if not is_success(attr_result):
                print("step_failed: server_get_attr")
                return 1
            structured = attr_summary.get("structured") or {}
            if structured.get("value") != 19.9:
                print("step_failed: scenario_did_not_apply")
                return 1

            for name, arguments in [
                (
                    "server_stop_scenario",
                    {
                        "instance_key": instance_key,
                        "scenario_name": scenario_name,
                    },
                ),
                (
                    "server_delete_scenario",
                    {
                        "instance_key": instance_key,
                        "scenario_name": scenario_name,
                    },
                ),
                ("server_stop_instance", {"instance_key": instance_key}),
                ("server_start_instance", {"instance_key": instance_key}),
                ("server_reset_instance", {"instance_key": instance_key}),
            ]:
                result = await session.call_tool(name, arguments)
                summary = summarize_result(result)
                print(f"\n[{name}]")
                print(summary)
                if not is_success(result):
                    print(f"step_failed: {name}")
                    return 1

    print("\nsmoke_result: ok")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    product_key = load_product_key(args.product_key)
    return anyio.run(
        run_smoke,
        args.python,
        args.spx_base_url,
        product_key,
        args.model_id,
        args.instance_key,
    )


if __name__ == "__main__":
    raise SystemExit(main())
