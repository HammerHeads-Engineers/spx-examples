# SPDX-License-Identifier: MIT
"""Bootstrap selected models into a running SPX server via the API."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import yaml
import requests

try:
    import spx_python
except Exception:  # pragma: no cover
    spx_python = None


DEFAULT_API = os.environ.get("SPX_API_URL", "http://localhost:8000")


def load_bundle(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def wait_for_server(api_url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    base = api_url.rstrip('/')
    candidates = [f"{base}/health", base]
    while time.monotonic() < deadline:
        for url in candidates:
            try:
                response = requests.get(url, timeout=3.0)
                if response.ok:
                    return
            except Exception:
                continue
        time.sleep(2.0)
    raise RuntimeError(f"SPX server at {api_url} did not become healthy within {timeout} seconds")


def bootstrap(bundle_path: Path, api_url: str, *, skip_instances: bool = False) -> None:
    bundle = load_bundle(bundle_path)
    models = bundle.get("models", [])
    instances = bundle.get("instances", [])
    start_instances = [str(key).strip() for key in bundle.get("start_instances", []) or [] if str(key).strip()]
    if not models:
        print("[bootstrap] No models defined in bundle; nothing to do.")
        return

    wait_for_server(api_url)
    if spx_python is not None:
        client = spx_python.init(address=api_url, product_key=bundle.get("license_key", ""))
        for entry in models:
            register_via_sdk(client, entry)
        if skip_instances:
            if instances:
                print("[bootstrap] Instance creation skipped (--skip-instances).")
            if start_instances:
                print("[bootstrap] Instance start skipped (--skip-instances).")
        else:
            for entry in instances:
                create_instance_via_sdk(client, entry)
            for instance_key in start_instances:
                start_instance_via_sdk(client, instance_key)
    else:
        register_via_http(api_url, bundle.get("license_key", ""), models)
        if instances:
            reason = "spx_python not available" if not skip_instances else "--skip-instances"
            print(f"[bootstrap] Instance creation skipped ({reason}).")
        if start_instances:
            print("[bootstrap] Instance start skipped (spx_python not available).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap models/instances into SPX server")
    parser.add_argument("--bundle", required=True, help="Path to bundle JSON produced by installer")
    parser.add_argument("--api-url", default=DEFAULT_API, help="SPX server API base URL")
    parser.add_argument(
        "--skip-instances",
        action="store_true",
        help="Register models only (do not create instances from bundle.json).",
    )
    args = parser.parse_args(argv)

    bootstrap(Path(args.bundle), args.api_url, skip_instances=bool(args.skip_instances))
    return 0


def register_via_sdk(client, entry: Dict[str, Any]) -> None:
    model_id = entry.get("id")
    model_path = Path(entry.get("path", ""))
    if not model_id or not model_path.exists():
        print(f"  - Skipping invalid entry: {entry}")
        return
    with model_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    client["models"][model_id] = payload
    print(f"  - Registered model {model_id} via SDK")


def create_instance_via_sdk(client, entry: Dict[str, Any]) -> None:
    model_id = entry.get("model_id")
    instance_key = entry.get("instance_key")
    if not model_id or not instance_key:
        return
    client["instances"][instance_key] = model_id
    print(f"  - Created instance {instance_key} from {model_id}")


def start_instance_via_sdk(client, instance_key: str) -> None:
    if not instance_key:
        return
    try:
        instance = client["instances"][instance_key]
    except Exception:
        print(f"  - Skipping start for {instance_key} (instance not found)")
        return
    try:
        instance.start()
        print(f"  - Started instance {instance_key}")
    except Exception as exc:
        print(f"  - Failed to start instance {instance_key}: {exc}")


def register_via_http(api_url: str, product_key: str, models: list[Dict[str, Any]]) -> None:
    session = requests.Session()
    if product_key:
        session.headers.update({"X-SPX-PRODUCT-KEY": product_key})
    for entry in models:
        model_id = entry.get("id")
        model_path = Path(entry.get("path", ""))
        if not model_id or not model_path.exists():
            print(f"  - Skipping invalid entry: {entry}")
            continue
        with model_path.open("r", encoding="utf-8") as handle:
            payload = handle.read()
        resp = session.post(
            f"{api_url.rstrip('/')}/models",
            headers={"Content-Type": "application/x-yaml"},
            params={"model_id": model_id},
            data=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        print(f"  - Registered model {model_id} via HTTP")


if __name__ == "__main__":
    raise SystemExit(main())
