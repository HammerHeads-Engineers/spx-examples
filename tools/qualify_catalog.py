"""Lifecycle qualification against a dedicated, empty SPX server.

This is real runtime evidence, not a static-validation certificate. Transport
interoperability and device fidelity remain separate model-specific tests.
"""

from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from tools.model_catalog import (
    CatalogError,
    digest,
    read_yaml,
    select_models,
    verify_catalog,
)


def _state(instance) -> str:
    state = instance.state
    return str(state).upper()


def _wait_running(instance):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = _state(instance)
        if state == "RUNNING":
            return
        if state == "FAULT":
            break
        time.sleep(0.1)
    raise CatalogError("Instance did not reach RUNNING")


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogError("Non-finite runtime telemetry")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def qualify_catalog(
    directory, base_url: str, *, allow_writes=False, model_ids=(), expected_server=None
):
    if not allow_writes:
        raise CatalogError(
            "Use --allow-runtime-writes only with a dedicated disposable SPX server"
        )
    url = urlsplit(base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise CatalogError(
            "Use a credential-free http(s) base URL; provide SPX_PRODUCT_KEY through the environment"
        )
    key = os.environ.get("SPX_PRODUCT_KEY", "")
    if not key:
        raise CatalogError("SPX_PRODUCT_KEY is required for runtime qualification")
    document = verify_catalog(directory)
    import requests
    import spx_python

    try:
        response = requests.get(
            base_url.rstrip("/") + "/api/versions",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        response.raise_for_status()
        server = response.json()["server_version"].removeprefix("v")
        if expected_server is not None and server != expected_server.removeprefix("v"):
            raise CatalogError(
                f"Expected server {expected_server}; endpoint reports {server}"
            )
        client = spx_python.init(address=base_url, product_key=key, transparent=False)
        models, instances = client["models"], client["instances"]
        if models.keys() or instances.keys():
            raise CatalogError(
                "Qualification requires empty model and instance registries; use a fresh disposable server"
            )
    except CatalogError:
        raise
    except Exception as exc:
        # Do not leak a URL, token or server response into public release artifacts.
        raise CatalogError(
            f"Cannot establish an authenticated qualification session ({type(exc).__name__})"
        ) from None
    selected = select_models(document, server, include_deprecated=True)
    if model_ids:
        unknown = set(model_ids) - {m["id"] for m in selected}
        if unknown:
            raise CatalogError(
                f"Unknown or incompatible diagnostic models: {sorted(unknown)}"
            )
        selected = [m for m in selected if m["id"] in model_ids]
    if not selected:
        raise CatalogError(
            f"No catalog models declare compatibility with server {server}"
        )
    results = []
    for model in selected:
        model_id = model["id"]
        instance_key = "catalog_qa_" + digest(model_id.encode())[:16]
        result = {
            "model_id": model_id,
            "registration": "NOT_RUN",
            "startup": "NOT_RUN",
            "behavior": "NOT_RUN",
            "lifecycle": "NOT_RUN",
            "cleanup": "NOT_RUN",
        }
        stage = "registration"
        try:
            definition = read_yaml(directory / "files" / model["path"])
            models[model_id] = definition
            result[stage] = "PASSED"
            stage = "startup"
            specs = definition.get("meta_parameters", {})
            if specs:
                missing = [
                    name
                    for name, spec in specs.items()
                    if isinstance(spec, dict)
                    and spec.get("required")
                    and "default" not in spec
                ]
                if missing:
                    raise CatalogError(
                        "Required meta parameters need qualification defaults"
                    )
                parameters = {
                    name: {"cycle": [spec["default"]]}
                    for name, spec in specs.items()
                    if isinstance(spec, dict) and "default" in spec
                }
                instances.generate(
                    template=model_id, count=1, name=instance_key, parameters=parameters
                )
            else:
                instances[instance_key] = model_id
            instance = instances[instance_key]
            instance.reset()
            instance.start()
            _wait_running(instance)
            result[stage] = "PASSED"
            stage = "behavior"
            for _ in range(3):
                instance.run()
                _finite(instance.get())
                if _state(instance) == "FAULT":
                    raise CatalogError("Instance faulted during polling")
            result[stage] = "PASSED"
            stage = "lifecycle"
            instance.stop()
            if _state(instance) == "RUNNING":
                raise CatalogError("Instance remained RUNNING after stop")
            instance.start()
            _wait_running(instance)
            result[stage] = "PASSED"
        except Exception as exc:
            result[stage] = "FAILED"
            result["error"] = (
                f"{stage} failed ({type(exc).__name__}); inspect the dedicated server logs"
            )
        finally:
            try:
                if instance_key in instances.keys():
                    instances[instance_key].stop()
                    del instances[instance_key]
                if model_id in models.keys():
                    del models[model_id]
                if models.keys() or instances.keys():
                    raise CatalogError("Registry cleanup incomplete")
                result["cleanup"] = "PASSED"
            except Exception:
                result["cleanup"] = "FAILED"
        results.append(result)
        if result["cleanup"] != "PASSED":
            break
    passed = len(results) == len(selected) and all(
        all(
            row[field] == "PASSED"
            for field in ("registration", "startup", "behavior", "lifecycle", "cleanup")
        )
        for row in results
    )
    return {
        "schema_version": 1,
        "status": "PASSED" if passed else "FAILED",
        "source_commit": document["source"]["commit"],
        "catalog_sha256": digest((directory / "catalog.json").read_bytes()),
        "server_version": server,
        "scope": "diagnostic-subset" if model_ids else "full-catalog",
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "checks": [
            "registration",
            "startup",
            "three-runtime-cycles",
            "finite-values",
            "stop-start",
            "cleanup",
        ],
        "results": results,
    }
