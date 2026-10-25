"""Required live qualification of every model selected by the installer.

Run against an isolated licensed stack with SPX_PAUSE_QUALIFICATION=1 and
SPX_PAUSE_MANIFEST pointing at its startup-models.json. No transports are
removed from model definitions; the installed models are used unchanged.
"""

import json
import os
from pathlib import Path
import time
import uuid

import pytest
import requests


pytestmark = pytest.mark.skipif(os.getenv("SPX_PAUSE_QUALIFICATION") != "1",
                               reason="opt-in live installed catalog qualification")


def _children(document):
    children = document["children"]
    return children if isinstance(children, dict) else {child["name"]: child for child in children}


@pytest.fixture(scope="module")
def live():
    key = os.getenv("SPX_PRODUCT_KEY")
    assert key, "SPX_PRODUCT_KEY is required; this release check cannot be skipped"
    manifest = os.getenv("SPX_PAUSE_MANIFEST")
    assert manifest, "SPX_PAUSE_MANIFEST must identify the selected installed catalog"
    models = json.loads(Path(manifest).read_text(encoding="utf-8-sig"))["models"]
    assert models, "The selected catalog is empty"
    session = requests.Session()
    session.trust_env = False
    session.headers["Authorization"] = "Bearer " + key
    base = os.environ.get("SPX_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v3/system"

    def call(method, path, data=None):
        response = session.request(method, base + path, json=data, timeout=30)
        assert response.ok, f"{method} {path}: HTTP {response.status_code}"
        result = response.json()
        if method == "POST":
            assert result.get("result") is not False, f"{method} {path}: lifecycle returned false"
        return result

    installed = _children(call("GET", "/models"))
    assert all(model["id"] in installed for model in models), "Installed catalog differs from the manifest"
    yield call, models
    session.close()


def test_every_selected_model_freezes_and_resumes(live, record_property):
    call, models = live
    failures = []
    checked = []
    for model in models:
        instance = "qa_pause_" + uuid.uuid4().hex[:10]
        path = "/instances/" + instance
        try:
            call("PUT", "/instances", {instance: {"type": model["id"]}})
            call("POST", path + "/method/start", {})
            time.sleep(0.15)
            call("POST", path + "/method/pause", {})

            def state():
                return call("GET", path)["attr"]["state"]["value"]

            def clock():
                return call("GET", path + "/attributes/__timer/attr/internal_value")["value"]

            def telemetry():
                # Protocol diagnostics may legitimately change during pause.
                attrs = _children(call("GET", path + "/attributes"))
                return {name: item["attr"]["internal_value"]["value"] for name, item in attrs.items()
                        if any(word in name for word in ("energy", "temperature", "pressure", "position", "speed"))
                        and not name.startswith(("k__", "cmd__", "_"))}

            frozen = clock()
            before = telemetry()
            counter = call("GET", path + "/polling/attr/polling_counter")["value"]
            interval = call("GET", path + "/polling/attr/interval")["value"]
            jitter = call("GET", path + "/polling/attr/jitter")["value"]
            assert interval >= 0 and jitter >= 0
            pause_wait = max(0.6, 5 * (interval + jitter))
            time.sleep(pause_wait)
            assert state() == "PAUSED", "Pause state changed in the background"
            assert clock() == frozen, "Clock advanced during Pause"
            assert call("GET", path + "/polling/attr/polling_counter")["value"] == counter, "Polling continued during Pause"
            assert telemetry() == before, "Physics or energy advanced during Pause"
            call("POST", path + "/method/run", {})
            assert state() == "PAUSED", "Run resumed background execution"
            stepped = clock()
            time.sleep(max(0.15, interval * 2))
            assert clock() == stepped, "Run launched a worker"
            call("POST", path + "/method/start", {})
            time.sleep(0.15)
            assert state() == "RUNNING", "Resume did not run"
            assert stepped < clock() < stepped + 0.5, "Resume reset time or included paused wall time"
            checked.append(model["id"])
        except Exception as error:
            failures.append(f"{model['id']}: {error}")
        finally:
            call("DELETE", path)
    record_property("selected_models", len(models))
    record_property("qualified_models", ",".join(checked))
    assert not failures, "\n".join(failures)
    assert len(checked) == len(models)
