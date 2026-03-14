# SPDX-License-Identifier: MIT
"""Unit tests for the manifest loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from installer.manifest import ManifestLoader


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog"
    catalog.mkdir()

    (catalog / "domains.yaml").write_text(
        textwrap.dedent(
            """\
            domains:
              - id: environment
                name: Environment
                description: Test domain
                path: library/domains/environment
            """
        ),
        encoding="utf-8",
    )
    (catalog / "models.yaml").write_text(
        textwrap.dedent(
            """\
            models:
              - id: sensor
                name: Sensor
                path: library/domains/environment/sensor/generic/sensor.yaml
                domain: environment
                domain_group: environment
                device_class: sensor
                vendor: generic
                protocols: [mqtt]
                services:
                  - id: mqtt_broker
                packages: [test_pack]
                profiles: [test_profile]
            """
        ),
        encoding="utf-8",
    )
    (catalog / "industries.yaml").write_text(
        textwrap.dedent(
            """\
            industries:
              - id: test_pack
                name: Test Pack
                description: Test description
                protocols: [mqtt]
                services: [mqtt_broker]
                profiles:
                  - profiles/test_pack/test_profile.yaml
                default_instances:
                  - model: sensor
                    instance: pack_sensor_01
                path: library/industries/test_pack
            """
        ),
        encoding="utf-8",
    )
    (catalog / "services.yaml").write_text(
        textwrap.dedent(
            """\
            services:
              - id: mqtt_broker
                name: MQTT
                protocol: mqtt
                description: Test broker
                ports:
                  - transport: tcp
                    host: 1883
                    container: 1883
                    purpose: telemetry
                deployment:
                  runtime: docker
                  image: eclipse-mosquitto:latest
                  container_name: mosquitto
            """
        ),
        encoding="utf-8",
    )

    return catalog


@pytest.fixture()
def profiles_dir(tmp_path: Path) -> Path:
    base = tmp_path / "profiles"
    pack_dir = base / "test_pack"
    pack_dir.mkdir(parents=True)

    (pack_dir / "test_profile.yaml").write_text(
        textwrap.dedent(
            """\
            name: test_profile
            description: Profile description
            models:
              - library/domains/environment/sensor/generic/sensor.yaml
            services:
              - mqtt_broker
            """
        ),
        encoding="utf-8",
    )
    return base


def test_manifest_loader_parses_catalog(
    tmp_path: Path, catalog_dir: Path, profiles_dir: Path
) -> None:
    loader = ManifestLoader(catalog_dir=catalog_dir, profiles_dir=profiles_dir)
    index = loader.load()

    assert "mqtt_broker" in index.services
    broker = index.services["mqtt_broker"]
    assert broker.deployment is not None
    assert broker.deployment.image == "eclipse-mosquitto:latest"

    assert "sensor" in index.models
    model = index.models["sensor"]
    assert model.path == Path("library/domains/environment/sensor/generic/sensor.yaml")
    assert model.services == ["mqtt_broker"]

    assert "test_pack" in index.industries
    assert index.industries["test_pack"].default_instances == [
        {"model": "sensor", "instance": "pack_sensor_01"}
    ]
    assert "test_profile" in index.profiles
