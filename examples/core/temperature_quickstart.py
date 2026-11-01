# SPDX-License-Identifier: MIT
"""Change one temperature input and remove only this example's own objects."""

from contextlib import redirect_stderr, redirect_stdout
import io
import math
import os
from pathlib import Path
import sys
import time
import uuid

import yaml

MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "templates/models/temperature_sensor.yaml"
)


class QuickstartError(RuntimeError):
    """A diagnostic safe to show without exposing server responses or credentials."""


def _cleanup(models, instances, model_key, instance_key):
    errors = []
    try:
        if instance_key in instances.keys():
            try:
                instances[instance_key].stop()
            finally:
                del instances[instance_key]
    except Exception:
        errors.append("instance")
    try:
        if model_key in models.keys():
            del models[model_key]
    except Exception:
        errors.append("model")
    if errors:
        raise QuickstartError(
            f"Cleanup incomplete; inspect only example objects {instance_key} and {model_key}."
        )


def run_example(client, definition, *, token=None):
    token = token or uuid.uuid4().hex
    model_key = "quickstart_temperature_" + token
    instance_key = model_key + "_instance"
    models, instances = client["models"], client["instances"]
    # Refuse existing names before entering cleanup, including on a repeat run.
    if model_key in models.keys() or instance_key in instances.keys():
        raise QuickstartError("Example names already exist; no objects were changed.")
    try:
        models[model_key] = definition
        instances[instance_key] = model_key
        instance = instances[instance_key]
        instance.reset()
        instance.start()
        deadline = time.monotonic() + 5
        while str(instance.state).upper() != "RUNNING":
            if time.monotonic() >= deadline or str(instance.state).upper() == "FAULT":
                raise QuickstartError("Example instance did not reach RUNNING.")
            time.sleep(0.1)
        instance.run()
        initial = float(instance["attributes"]["temperature_c"].internal_value)
        instance["attributes"]["k__temperature_c"].internal_value = 37.5
        instance.run()
        changed = float(instance["attributes"]["temperature_c"].internal_value)
        if not math.isclose(initial, 20.0) or not math.isclose(changed, 37.5):
            raise QuickstartError("Control-to-telemetry verification failed.")
        return initial, changed
    finally:
        _cleanup(models, instances, model_key, instance_key)


def main():
    key = os.environ.get("SPX_PRODUCT_KEY", "")
    if not key:
        print(
            "Set SPX_PRODUCT_KEY for your test server before running the example.",
            file=sys.stderr,
        )
        return 1
    try:
        # Some client versions print raw server faults. Show only our own safe
        # diagnostics; do not place credentials/server responses in tutorial output.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            import spx_python

            client = spx_python.init(
                address=os.environ.get("SPX_BASE_URL", "http://localhost:8000"),
                product_key=key,
                transparent=False,
            )
            definition = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))
            initial, changed = run_example(client, definition)
    except QuickstartError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Temperature example failed ({type(exc).__name__}). "
            "Check the test server URL, product key, license capacity and server logs locally.",
            file=sys.stderr,
        )
        return 1
    print(f"Initial temperature: {initial:.1f} degC")
    print(f"After setting k__temperature_c: {changed:.1f} degC")
    print("PASS: input changed telemetry; example instance and model removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
