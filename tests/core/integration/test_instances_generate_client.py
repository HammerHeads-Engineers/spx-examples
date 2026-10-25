# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Core integration coverage for Instances.generate exposed via the spx_python client."""

from __future__ import annotations

import os
import socket
import time
import unittest
import uuid
from typing import Dict, List

import requests

from tests.common.spx_utils import ensure_model

try:
    import spx_python  # type: ignore
except Exception:  # pragma: no cover - optional dependency in some envs
    spx_python = None  # type: ignore


MODEL_DEF: Dict[str, object] = {
    "name": "instances_generate_template",
    "description": "Minimal template to exercise Instances.generate via API",
    "meta_parameters": {
        "port": {"type": "int", "required": True},
        "zone": {"type": "str", "default": "A"},
    },
    "attributes": {
        "port": "$param(port)",
        "zone": "$param(zone)",
        "label": "zone-$param(zone)-port-$param(port)",
    },
}

MODEL_DEF_KNX: Dict[str, object] = {
    "name": "knx_param_template",
    "description": "KNX template with parameterised group addresses",
    "meta_parameters": {
        "temp_ga": {"type": "str", "required": True},
        "cmd_ga": {"type": "str", "required": True},
        "zone": {"type": "str", "default": "Z"},
    },
    "attributes": {
        "temp_c": 21.0,
        "cmd_c": 21.0,
        "zone": "$param(zone)",
    },
    "communication": [
        {
            "knx_ip": {
                "router": {"host": "knx_gateway", "port": 3671, "route_back": True},
                "bindings": [
                    {
                        "name": "temp",
                        "direction": "outbound",
                        "group_address": "$param(temp_ga)",
                        "dpt": "9.001",
                        "read_attribute": "#attr(temp_c)",
                    },
                    {
                        "name": "command",
                        "direction": "inbound",
                        "group_address": "$param(cmd_ga)",
                        "dpt": "9.001",
                        "write_attribute": "#attr(cmd_c)",
                    },
                ],
            }
        }
    ],
}


def _server_available(api_url: str) -> bool:
    try:
        resp = requests.get(api_url.rstrip("/") + "/health", timeout=2.0)
        return resp.ok
    except Exception:
        return False


def _knx_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


class TestInstancesGenerateClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if spx_python is None:
            raise unittest.SkipTest("spx_python not installed; install it to run SPX integration tests.")

        cls._product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not cls._product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run SPX integration tests.")

        cls._api_url = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
        if not _server_available(cls._api_url):
            raise unittest.SkipTest(f"SPX server not reachable at {cls._api_url}")

        cls._client = spx_python.init(address=cls._api_url, product_key=cls._product_key)

        cls._model_key = f"tests__instances_generate_{uuid.uuid4().hex[:8]}"
        ensure_model(cls._client, cls._model_key, MODEL_DEF)

        cls._instances = cls._client["instances"]
        cls._name_fmt = f"gen_{int(time.time())}" + "_{zone}_{i1}_p{port}"
        cls._gen_params = {
            "port": {"seq": {"start": 6020, "step": 2}},
            "zone": {"cycle": ["north", "south"]},
        }
        cls._expected: List[Dict[str, object]] = []
        for i in range(3):
            port = 6020 + 2 * i
            zone = "north" if i % 2 == 0 else "south"
            cls._expected.append(
                {
                    "name": cls._name_fmt.format(i=i, i1=i + 1, port=port, zone=zone),
                    "port": port,
                    "zone": zone,
                    "label": f"zone-{zone}-port-{port}",
                }
            )

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "_instances"):
            return
        for entry in getattr(cls, "_expected", []):
            try:
                del cls._instances[entry["name"]]  # type: ignore[index]
            except Exception:
                pass

    def test_generate_creates_parameterised_instances(self):
        created = self._instances.generate(
            template=self._model_key,
            count=len(self._expected),
            name=self._name_fmt,
            parameters=self._gen_params,
        )
        if isinstance(created, dict) and "result" in created:
            created_names = created["result"]
        else:
            created_names = created

        for entry in self._expected:
            name = entry["name"]
            if created_names:
                self.assertIn(name, created_names)

            inst = self._instances[name]
            attrs_client = inst["attributes"]

            port_attr = attrs_client["port"]
            zone_attr = attrs_client["zone"]
            label_attr = attrs_client["label"]

            port_val = zone_val = label_val = None
            deadline = time.time() + 3.0
            while time.time() < deadline:
                port_val = getattr(port_attr, "internal_value", None)
                zone_val = getattr(zone_attr, "internal_value", None)
                label_val = getattr(label_attr, "internal_value", None)
                if port_val is not None and zone_val is not None and label_val is not None:
                    break
                time.sleep(0.1)

            self.assertEqual(port_val, entry["port"])
            self.assertEqual(zone_val, entry["zone"])
            self.assertEqual(label_val, entry["label"])


class TestKnxInstancesGenerateClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if spx_python is None:
            raise unittest.SkipTest("spx_python not installed; install it to run SPX integration tests.")

        cls._product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not cls._product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run SPX integration tests.")

        cls._api_url = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
        if not _server_available(cls._api_url):
            raise unittest.SkipTest(f"SPX server not reachable at {cls._api_url}")

        knx_host = os.environ.get("KNX_TEST_HOST", "127.0.0.1")
        knx_port = int(os.environ.get("KNX_TEST_PORT", "3671"))
        if not _knx_available(knx_host, knx_port):
            raise unittest.SkipTest(f"KNX server not reachable at {knx_host}:{knx_port}")

        cls._client = spx_python.init(address=cls._api_url, product_key=cls._product_key)

        cls._model_key = f"tests__knx_generate_{uuid.uuid4().hex[:8]}"
        ensure_model(cls._client, cls._model_key, MODEL_DEF_KNX)

        cls._instances = cls._client["instances"]
        cls._name_fmt = f"knx_gen_{int(time.time())}" + "_{zone}_{i1}"
        cls._gen_params = {
            "temp_ga": {"template": "1/5/{i1}"},
            "cmd_ga": {"template": "1/6/{i1}"},
            "zone": {"cycle": ["north", "south"]},
        }
        cls._expected: List[Dict[str, object]] = []
        for i in range(2):
            zone = "north" if i % 2 == 0 else "south"
            cls._expected.append(
                {
                    "name": cls._name_fmt.format(i=i, i1=i + 1, zone=zone),
                    "temp_ga": f"1/5/{i + 1}",
                    "cmd_ga": f"1/6/{i + 1}",
                    "zone": zone,
                }
            )

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "_instances"):
            return
        for entry in getattr(cls, "_expected", []):
            try:
                del cls._instances[entry["name"]]  # type: ignore[index]
            except Exception:
                pass

    def _binding_group_addresses(self, inst_name: str) -> Dict[str, str]:
        bindings_client = self._instances[inst_name]["communication"]["knx_ip"]["bindings"]
        doc = bindings_client.get()
        children = doc.get("children", []) if isinstance(doc, dict) else []
        out: Dict[str, str] = {}
        for child in children:
            if not isinstance(child, dict):
                continue
            name = child.get("name")
            ga = child.get("group_address")
            if ga is None:
                ga = child.get("attr", {}).get("group_address", {}).get("value") if isinstance(child.get("attr"), dict) else None
            if name and ga:
                out[name] = ga
        return out

    def test_generate_knx_group_addresses_resolved(self):
        created = self._instances.generate(
            template=self._model_key,
            count=len(self._expected),
            name=self._name_fmt,
            parameters=self._gen_params,
        )
        if isinstance(created, dict) and "result" in created:
            created_names = created["result"]
        else:
            created_names = created

        for entry in self._expected:
            name = entry["name"]
            if created_names:
                self.assertIn(name, created_names)

            bindings = self._binding_group_addresses(name)
            self.assertEqual(bindings.get("temp"), entry["temp_ga"])
            self.assertEqual(bindings.get("command"), entry["cmd_ga"])
