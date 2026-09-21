# SPDX-License-Identifier: MIT
"""Bootstrap selected models into a running SPX server via the API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml
import requests

try:
    import spx_python
except Exception:  # pragma: no cover
    spx_python = None


DEFAULT_API = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
_PRODUCT_KEY_FOR_REDACTION = ""


@dataclass
class BootstrapReport:
    models_created: int = 0
    models_skipped: int = 0
    instances_created: int = 0
    instances_skipped: int = 0
    failures: int = 0


class InstanceLimitExceeded(RuntimeError):
    """The server rejected an instance because the license limit was reached."""


def redact(value: Any) -> str:
    text = str(value or "")
    product_key = _PRODUCT_KEY_FOR_REDACTION or os.environ.get("SPX_PRODUCT_KEY", "").strip()
    if product_key:
        text = text.replace(product_key, "<redacted>")
    text = re.sub(r"(?i)(--product-key\s+)[^\s]+", r"\1<redacted>", text)
    return text.replace("SPX_PRODUCT_KEY=", "SPX_PRODUCT_KEY=<redacted>")


def _read_env_file(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        if name.strip() == "SPX_PRODUCT_KEY":
            return value.strip().strip('"').strip("'")
    return ""


def resolve_product_key(bundle: Dict[str, Any], bundle_path: Path) -> str:
    """Read the key from the environment/.env, with legacy bundle support."""

    global _PRODUCT_KEY_FOR_REDACTION
    value = (
        os.environ.get("SPX_PRODUCT_KEY", "").strip()
        or _read_env_file(bundle_path.parent / ".env")
        or str(bundle.get("license_key", "")).strip()
    )
    _PRODUCT_KEY_FOR_REDACTION = value
    return value


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

    report = BootstrapReport()
    wait_for_server(api_url)
    product_key = resolve_product_key(bundle, bundle_path)
    if spx_python is not None:
        client = spx_python.init(address=api_url, product_key=product_key)
        model_payloads: Dict[str, Dict[str, Any]] = {}
        try:
            for entry in models:
                payload, created = register_via_sdk(client, entry, bundle_path.parent)
                if payload and isinstance(payload, dict):
                    model_id = entry.get("id")
                    if isinstance(model_id, str) and model_id:
                        model_payloads[model_id] = payload
                        if created:
                            report.models_created += 1
                        else:
                            report.models_skipped += 1
        except Exception as exc:
            report.failures += 1
            _print_report(report)
            raise RuntimeError(f"stage=model: {redact(exc)}") from exc
        if skip_instances:
            if instances:
                print("[bootstrap] Instance creation skipped (--skip-instances).")
            if start_instances:
                print("[bootstrap] Instance start skipped (--skip-instances).")
        else:
            try:
                for entry in instances:
                    created = create_instance_via_sdk(client, entry, model_payloads, report)
                    if not created:
                        report.instances_skipped += 1
            except Exception as exc:
                report.failures += 1
                _print_report(report)
                if isinstance(exc, InstanceLimitExceeded):
                    raise InstanceLimitExceeded(f"stage=instance: {redact(exc)}") from exc
                raise RuntimeError(f"stage=instance: {redact(exc)}") from exc
            try:
                for instance_key in start_instances:
                    start_instance_via_sdk(client, instance_key)
            except Exception as exc:
                report.failures += 1
                _print_report(report)
                raise RuntimeError(f"stage=start: {redact(exc)}") from exc
    else:
        register_via_http(api_url, product_key, models, bundle_path.parent)
        if instances:
            reason = "spx_python not available" if not skip_instances else "--skip-instances"
            print(f"[bootstrap] Instance creation skipped ({reason}).")
        if start_instances:
            print("[bootstrap] Instance start skipped (spx_python not available).")
    _print_report(report)


def _print_report(report: BootstrapReport) -> None:
    print(
        "[bootstrap] Summary: "
        f"models created={report.models_created}, skipped={report.models_skipped}; "
        f"instances created={report.instances_created}, skipped={report.instances_skipped}, "
        f"failed={report.failures}"
    )


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

    try:
        bootstrap(Path(args.bundle), args.api_url, skip_instances=bool(args.skip_instances))
    except Exception as exc:
        print(f"[bootstrap] ERROR: {redact(exc)}", file=sys.stderr)
        return 1
    return 0


def _resolve_model_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def register_via_sdk(
    client,
    entry: Dict[str, Any],
    base_dir: Path | None = None,
) -> tuple[Optional[Dict[str, Any]], bool]:
    model_id = entry.get("id")
    model_path = _resolve_model_path(str(entry.get("path", "")), base_dir or Path.cwd())
    if not model_id or not model_path.exists():
        print(f"  - Skipping invalid entry: {entry}")
        return None, False
    with model_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    existing = _lookup_model(client, str(model_id))
    client["models"][model_id] = payload
    print(f"  - {'Updated' if existing is not None else 'Registered'} model {model_id} via SDK")
    return payload, existing is None


def _lookup_model(client, model_id: str):
    return _lookup_collection_item(client["models"], model_id)


def _meta_defaults(payload: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    meta = payload.get("meta_parameters", {})
    if not isinstance(meta, dict):
        return {}, []
    params: Dict[str, Any] = {}
    missing: list[str] = []
    for name, spec in meta.items():
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            params[name] = {"cycle": [spec.get("default")]}
        elif spec.get("required") is True:
            missing.append(name)
    return params, missing


def create_instance_via_sdk(
    client,
    entry: Dict[str, Any],
    model_payloads: Dict[str, Dict[str, Any]],
    report: BootstrapReport | None = None,
) -> bool:
    model_id = entry.get("model_id")
    instance_key = entry.get("instance_key")
    if not model_id or not instance_key:
        return False
    existing = _lookup_instance(client, str(instance_key))
    if existing is not None:
        existing_model = _instance_model_id(existing)
        if existing_model == str(model_id):
            print(f"  - Skipped existing instance {instance_key} ({model_id})")
            return False
        raise RuntimeError(
            f"Instance conflict: {instance_key} already exists for model "
            f"{existing_model or '<unknown>'}, requested {model_id}"
        )
    payload = model_payloads.get(model_id, {})
    has_meta = isinstance(payload, dict) and bool(payload.get("meta_parameters"))
    if has_meta:
        params, missing = _meta_defaults(payload)
        if missing:
            raise RuntimeError(
                f"Missing defaults for required meta_parameters in {model_id}: {', '.join(missing)}"
            )
        if params:
            try:
                client["instances"].generate(
                    template=model_id,
                    count=1,
                    name=instance_key,
                    parameters=params,
                )
            except Exception as exc:
                if "limit_exceeded" in str(exc).lower() or "limit exceeded" in str(exc).lower():
                    raise InstanceLimitExceeded(
                        f"Community instance limit reached while creating {instance_key}"
                    ) from exc
                raise
            print(f"  - Generated instance {instance_key} from {model_id}")
            if report is not None:
                report.instances_created += 1
            return True
    try:
        client["instances"][instance_key] = model_id
    except Exception as exc:
        if "limit_exceeded" in str(exc).lower() or "limit exceeded" in str(exc).lower():
            raise InstanceLimitExceeded(
                f"Community instance limit reached while creating {instance_key}"
            ) from exc
        raise
    print(f"  - Created instance {instance_key} from {model_id}")
    if report is not None:
        report.instances_created += 1
    return True


def _lookup_instance(client, instance_key: str):
    return _lookup_collection_item(client["instances"], instance_key)


def _lookup_collection_item(collection, key: str):
    """Look up a child without issuing a noisy GET for a missing child.

    Recent spx-python clients implement ``key in collection`` as one GET of
    the collection followed by a local child-name check. Calling
    ``collection[key]`` first causes the client to log an expected 404 for
    every model and instance that bootstrap is about to create. Plain dicts
    and the small test doubles used by older clients do not necessarily
    implement membership, so they retain the direct lookup fallback.
    """

    contains = getattr(collection, "__contains__", None)
    if contains is not None:
        try:
            if key not in collection:
                return None
        except Exception:
            # A non-standard client may not support collection membership;
            # fall through to its traditional item lookup.
            pass
    try:
        return collection[key]
    except Exception:
        return None


def _instance_model_id(instance: Any) -> str:
    if isinstance(instance, str):
        return instance
    if isinstance(instance, dict):
        for key in ("model_id", "model", "modelId", "template"):
            if instance.get(key):
                return str(instance[key])
    for key in ("model_id", "model", "template"):
        value = getattr(instance, key, None)
        if isinstance(value, str) and value:
            return value
    try:
        document = instance.get()
    except Exception:
        document = None
    if isinstance(document, dict):
        for key in ("model_id", "model", "modelId", "template"):
            value = document.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def start_instance_via_sdk(client, instance_key: str) -> None:
    if not instance_key:
        return
    try:
        instance = client["instances"][instance_key]
    except Exception as exc:
        raise RuntimeError(f"Instance {instance_key} was not found for start") from exc
    try:
        instance.start()
        print(f"  - Started instance {instance_key}")
    except Exception as exc:
        raise RuntimeError(f"Failed to start instance {instance_key}: {redact(exc)}") from exc


def register_via_http(
    api_url: str,
    product_key: str,
    models: list[Dict[str, Any]],
    base_dir: Path | None = None,
) -> None:
    session = requests.Session()
    if product_key:
        session.headers.update({"X-SPX-PRODUCT-KEY": product_key})
    for entry in models:
        model_id = entry.get("id")
        model_path = _resolve_model_path(str(entry.get("path", "")), base_dir or Path.cwd())
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
        if getattr(resp, "status_code", 0) == 409:
            print(f"  - Skipped existing model {model_id} via HTTP")
            continue
        resp.raise_for_status()
        print(f"  - Registered model {model_id} via HTTP")


if __name__ == "__main__":
    raise SystemExit(main())
