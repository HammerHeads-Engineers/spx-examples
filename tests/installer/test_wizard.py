# SPDX-License-Identifier: MIT
"""Tests for the console wizard."""

from __future__ import annotations


import pytest

from installer.manifest import (
    DomainManifest,
    IndustryManifest,
    ManifestIndex,
    ModelManifest,
    ProfileManifest,
    ServiceDeployment,
    ServiceManifest,
    ServicePort,
)
from installer.wizard import InstallerWizard


@pytest.fixture(autouse=True)
def _product_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPX_PRODUCT_KEY", "TEST-KEY")


@pytest.fixture()
def manifest_index() -> ManifestIndex:
    services = {
        "mqtt_broker": ServiceManifest(
            id="mqtt_broker",
            name="MQTT Broker",
            protocol="mqtt",
            description="Test broker",
            ports=[ServicePort(transport="tcp", host=1883, container=1883, purpose="telemetry")],
            deployment=ServiceDeployment(runtime="docker", image="eclipse-mosquitto", container_name="mosquitto"),
        ),
    }
    models = {
        "sensor": ModelManifest(
            id="sensor",
            name="Sensor",
            path="library/domains/iot/sensor.yaml",
            domain="iot",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            packages=["pack_a"],
            profiles=["profile_a"],
        )
    }
    domains = {
        "iot": DomainManifest(
            id="iot",
            name="IoT",
            description="IoT domain",
            path="library/domains/iot",
        )
    }
    industries = {
        "pack_a": IndustryManifest(
            id="pack_a",
            name="Pack A",
            description="Pack description",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            profiles=["profile_a"],
            path="library/industries/pack_a",
        )
    }
    profiles = {
        "profile_a": ProfileManifest(
            id="profile_a",
            pack_id="pack_a",
            name="Profile A",
            description="Profile description",
            models=["library/domains/iot/sensor.yaml"],
            services=["mqtt_broker"],
            path="profiles/pack_a/profile_a.yaml",
        )
    }
    return ManifestIndex(
        services=services,
        models=models,
        domains=domains,
        industries=industries,
        profiles=profiles,
    )


def test_wizard_with_inputs(monkeypatch: pytest.MonkeyPatch, manifest_index: ManifestIndex, capsys) -> None:
    # Mock loader to return our manifest index
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "1", "", "n", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()

    assert selection.packages == ["pack_a"]
    assert selection.profiles == ["profile_a"]
    assert selection.protocols == []
    assert selection.install_examples is True
    assert selection.install_spx_ui is False
    assert selection.offline_bundle is False
    assert selection.license_key == "TEST-KEY"
    assert selection.model_ids == ["sensor"]
    assert selection.service_ids == ["mqtt_broker"]


def test_wizard_protocol_selection(monkeypatch: pytest.MonkeyPatch, manifest_index: ManifestIndex, capsys) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())
    inputs = iter(["0", "1", "y", "y", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()
    assert selection.packages == []
    assert selection.protocols == ["mqtt"]
    assert selection.install_examples is False
    assert selection.install_spx_ui is True
    assert selection.offline_bundle is True
    assert selection.license_key == "TEST-KEY"
    assert selection.model_ids == []
    assert selection.service_ids == ["mqtt_broker"]
