# SPDX-License-Identifier: MIT
"""Unit tests for installer CLI non-interactive generate mode."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import installer.generator as generator
from installer import cli


@pytest.fixture()
def manifest_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    repo_root = tmp_path / "repo"
    model_dir = repo_root / "library" / "domains" / "iot"
    model_dir.mkdir(parents=True)
    (model_dir / "sensor.yaml").write_text("name: dummy_sensor\n", encoding="utf-8")

    catalog_dir = repo_root / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "domains.yaml").write_text(
        textwrap.dedent(
            """\
            domains:
              - id: iot
                name: IoT
                description: Test domain
                path: library/domains/iot
            """
        ),
        encoding="utf-8",
    )
    (catalog_dir / "models.yaml").write_text(
        textwrap.dedent(
            """\
            models:
              - id: sensor
                name: Sensor
                path: library/domains/iot/sensor.yaml
                domain: iot
                protocols: [mqtt]
                services:
                  - id: mqtt_broker
                packages: [test_pack]
                profiles: [test_profile]
            """
        ),
        encoding="utf-8",
    )
    (catalog_dir / "industries.yaml").write_text(
        textwrap.dedent(
            """\
            industries:
              - id: test_pack
                name: Test Pack
                description: Pack description
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
    (catalog_dir / "services.yaml").write_text(
        textwrap.dedent(
            """\
            services:
              - id: mqtt_broker
                name: MQTT Broker
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
                  container_name: mosquitto-test
            """
        ),
        encoding="utf-8",
    )

    profiles_dir = repo_root / "profiles"
    pack_profiles_dir = profiles_dir / "test_pack"
    pack_profiles_dir.mkdir(parents=True)
    (pack_profiles_dir / "test_profile.yaml").write_text(
        textwrap.dedent(
            """\
            name: test_profile
            description: Profile description
            models:
              - library/domains/iot/sensor.yaml
            services:
              - mqtt_broker
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generator.paths, "repo_root", lambda: repo_root)
    return {"repo_root": repo_root, "catalog_dir": catalog_dir, "profiles_dir": profiles_dir}


def test_generate_noninteractive_packages_prints_json_and_creates_artifacts(
    tmp_path: Path,
    manifest_dirs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)

    output_dir = tmp_path / "out"
    rc = cli.main(
        [
            "generate",
            "--catalog",
            str(manifest_dirs["catalog_dir"]),
            "--profiles",
            str(manifest_dirs["profiles_dir"]),
            "--output",
            str(output_dir),
            "--packages",
            "test_pack",
            "--product-key",
            "SECRET-KEY",
            "--print-selection",
            "json",
            "--no-start",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert json.loads(captured.out)["packages"] == ["test_pack"]
    selection = json.loads(captured.out)
    assert selection["models"] == ["sensor"]
    assert selection["services"] == ["mqtt_broker"]
    assert selection["instances"] == [{"model_id": "sensor", "instance_key": "pack_sensor_01"}]
    assert selection["product_key_present"] is True
    assert "SECRET-KEY" not in captured.out
    assert "SECRET-KEY" not in captured.err

    assert (output_dir / "docker-compose.generated.yml").exists()
    assert (output_dir / ".env").read_text(encoding="utf-8").strip() == "SPX_PRODUCT_KEY=SECRET-KEY"
    assert (output_dir / "bundle.json").exists()
    assert (output_dir / "spx-start.sh").exists()
    assert (output_dir / "spx-stop.sh").exists()
    assert (output_dir / "spx-start.ps1").exists()
    assert (output_dir / "spx-stop.ps1").exists()
    assert (output_dir / "bootstrap_runner.py").exists()


def test_generate_allows_missing_product_key_when_flag_set(
    tmp_path: Path,
    manifest_dirs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)

    output_dir = tmp_path / "out"
    rc = cli.main(
        [
            "generate",
            "--catalog",
            str(manifest_dirs["catalog_dir"]),
            "--profiles",
            str(manifest_dirs["profiles_dir"]),
            "--output",
            str(output_dir),
            "--packages",
            "test_pack",
            "--allow-missing-product-key",
            "--print-selection",
            "json",
            "--no-start",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    selection = json.loads(captured.out)
    assert selection["product_key_present"] is False
    assert (output_dir / ".env").read_text(encoding="utf-8").strip() == "SPX_PRODUCT_KEY=REPLACE_ME"


def test_generate_requires_product_key_by_default(
    tmp_path: Path,
    manifest_dirs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)

    output_dir = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "generate",
                "--catalog",
                str(manifest_dirs["catalog_dir"]),
                "--profiles",
                str(manifest_dirs["profiles_dir"]),
                "--output",
                str(output_dir),
                "--packages",
                "test_pack",
                "--no-start",
            ]
        )
    assert "Missing SPX product key" in str(exc.value)

