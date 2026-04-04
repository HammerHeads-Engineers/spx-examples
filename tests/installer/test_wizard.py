# SPDX-License-Identifier: MIT
"""Tests for the console wizard."""

from __future__ import annotations

import pytest

from installer import manifest
from installer.wizard import InstallerWizard


@pytest.fixture(autouse=True)
def _product_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPX_PRODUCT_KEY", "TEST-KEY")


@pytest.fixture()
def manifest_index() -> manifest.ManifestIndex:
    services = {
        "mqtt_broker": manifest.ServiceManifest(
            id="mqtt_broker",
            name="MQTT Broker",
            protocol="mqtt",
            description="Test broker",
            ports=[
                manifest.ServicePort(
                    transport="tcp", host=1883, container=1883, purpose="telemetry"
                )
            ],
            deployment=manifest.ServiceDeployment(
                runtime="docker", image="eclipse-mosquitto", container_name="mosquitto"
            ),
        ),
    }
    models = {
        "sensor": manifest.ModelManifest(
            id="sensor",
            name="Sensor",
            path="library/domains/environment/sensor/generic/sensor.yaml",
            domain="environment",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            packages=["pack_a"],
            profiles=["profile_a"],
            domain_group="environment",
            device_class="sensor",
            vendor="generic",
        )
    }
    domains = {
        "environment": manifest.DomainManifest(
            id="environment",
            name="Environment",
            description="Environment domain",
            path="library/domains/environment",
        )
    }
    industries = {
        "pack_a": manifest.IndustryManifest(
            id="pack_a",
            name="Pack A",
            description="Pack description",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            profiles=["profile_a"],
            path="library/industries/pack_a",
            default_instances=[{"model": "sensor", "instance": "pack_a_sensor_01"}],
            start_instances=["pack_a_sensor_01"],
        )
    }
    profiles = {
        "profile_a": manifest.ProfileManifest(
            id="profile_a",
            pack_id="pack_a",
            name="Profile A",
            description="Profile description",
            models=["library/domains/environment/sensor/generic/sensor.yaml"],
            services=["mqtt_broker"],
            path="profiles/pack_a/profile_a.yaml",
        )
    }
    return manifest.ManifestIndex(
        services=services,
        models=models,
        domains=domains,
        industries=industries,
        profiles=profiles,
    )


def test_wizard_with_inputs(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    # Mock loader to return our manifest index
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()

    assert selection.packages == ["pack_a"]
    assert selection.profiles == []
    assert selection.protocols == []
    assert selection.install_examples is True
    assert selection.instances == []
    assert selection.start_instances == []
    assert selection.install_spx_ui is False
    assert selection.offline_bundle is True
    assert selection.license_key == "TEST-KEY"
    assert selection.model_ids == ["sensor"]
    assert selection.service_ids == ["mqtt_broker"]


def test_wizard_can_opt_in_to_default_instances(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "", "", "y", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()

    assert selection.packages == ["pack_a"]
    assert selection.install_examples is True
    assert selection.instances == [{"model_id": "sensor", "instance_key": "pack_a_sensor_01"}]
    assert selection.start_instances == ["pack_a_sensor_01"]
    assert selection.offline_bundle is True


def test_wizard_can_select_quickstart_profiles(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "1", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()

    assert selection.packages == ["pack_a"]
    assert selection.profiles == ["profile_a"]
    assert selection.install_examples is True
    assert selection.model_ids == ["sensor"]
    assert selection.service_ids == ["mqtt_broker"]
    assert selection.offline_bundle is True


def test_wizard_can_select_all_quickstart_profiles(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "a", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()

    assert selection.packages == ["pack_a"]
    assert selection.profiles == ["profile_a"]


def test_wizard_protocol_selection(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())
    inputs = iter(["0", "1", "", "", "", ""])
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


def test_wizard_masks_product_key_in_output(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)

    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(
        "getpass.getpass",
        lambda _: "COAUA-AAGRC-RWIUB-MRKIB-UMSHS-H7ZCU",
    )

    selection = wizard.run()
    captured = capsys.readouterr()

    assert selection.license_key == "COAUA-AAGRC-RWIUB-MRKIB-UMSHS-H7ZCU"
    assert "COAUA-AAGRC-RWIUB-MRKIB-UMSHS-H7ZCU" not in captured.out
    assert "SPX product key:" in captured.out
    assert "*******************************7ZCU" in captured.out


def test_wizard_masks_env_product_key_in_output(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())

    inputs = iter(["1", "", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    selection = wizard.run()
    captured = capsys.readouterr()

    assert selection.license_key == "TEST-KEY"
    assert "Detected SPX_PRODUCT_KEY in environment:" in captured.out
    assert "TEST-KEY" not in captured.out
    assert "****-KEY" in captured.out


def test_wizard_prints_runtime_notices(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())
    inputs = iter(["1", "", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("installer.wizard.current_platform_name", lambda: "windows")

    wizard.run()
    captured = capsys.readouterr()

    assert "Runtime & third-party notices:" in captured.out
    assert "Docker Desktop is required on this platform" in captured.out
    assert "Eclipse Mosquitto" in captured.out


def test_wizard_banner_includes_installer_version(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())
    inputs = iter(["1", "", "", "", "n", "n", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(wizard, "_resolve_installer_version", lambda: "9.9.9-test")

    wizard.run()
    captured = capsys.readouterr()

    assert "SPX Installation Wizard" in captured.out
    assert "Version 9.9.9-test" in captured.out


def test_prompt_packages_uses_compact_overview(
    monkeypatch: pytest.MonkeyPatch, manifest_index: manifest.ManifestIndex, capsys
) -> None:
    class FakeLoader:
        def load(self):
            return manifest_index

    wizard = InstallerWizard(loader=FakeLoader())
    monkeypatch.setattr("builtins.input", lambda _: "1")

    packages, protocols = wizard._prompt_packages(manifest_index.industries, manifest_index)
    captured = capsys.readouterr()

    assert packages == ["pack_a"]
    assert protocols == []
    assert "Pack description" in captured.out
    assert "[MQTT | 1 protocols, 1 services]" in captured.out
    assert "Protocols:" not in captured.out
    assert "Services:" not in captured.out


def test_package_protocol_badges_use_embedded_lab_highlights(
    manifest_index: manifest.ManifestIndex,
) -> None:
    wizard = InstallerWizard()
    manifest_value = manifest.IndustryManifest(
        id="embedded_lab_pack",
        name="Embedded & Lab Pack",
        description="BLE, MQTT/LwM2M and SCPI devices for firmware CI and hardware-in-the-loop labs.",
        protocols=["ble", "mqtt", "lwm2m", "coap", "scpi", "modbus"],
        services=["btvirt_adapter", "mqtt_broker", "lwm2m_server", "scpi_tcp_stack", "modbus_tcp_gateway"],
        profiles=["mhealth_ci"],
        path="library/industries/embedded_lab_pack",
    )

    badges = wizard._package_protocol_badges(manifest_value)

    assert badges == ["ASCII", "SCPI", "BLE", "Modbus"]


def test_package_overview_uses_embedded_lab_display_summary() -> None:
    wizard = InstallerWizard()
    manifest_value = manifest.IndustryManifest(
        id="embedded_lab_pack",
        name="Embedded & Lab Pack",
        description="BLE, MQTT/LwM2M and SCPI devices for firmware CI and hardware-in-the-loop labs.",
        protocols=["ble", "mqtt", "lwm2m", "coap", "scpi", "modbus"],
        services=["btvirt_adapter", "mqtt_broker", "lwm2m_server", "scpi_tcp_stack", "modbus_tcp_gateway"],
        profiles=["mhealth_ci"],
        path="library/industries/embedded_lab_pack",
    )

    overview = wizard._format_package_overview(manifest_value, 120)

    assert "Modbus TCP, SCPI, BLE, MQTT/LwM2M" in overview
