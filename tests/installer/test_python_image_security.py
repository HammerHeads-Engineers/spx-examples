# SPDX-License-Identifier: MIT
import pytest
from types import SimpleNamespace

import yaml

from tools import verify_python_images as images


def test_catalog_includes_all_shipped_python_providers():
    shipped = images.shipped_images()
    assert any("spx-server" in image for image in shipped)
    assert any("home-assistant/home-assistant" in image for image in shipped)
    assert any("python-matter-server" in image for image in shipped)


def write_compose(tmp_path, **services):
    path = tmp_path / "docker-compose.generated.yml"
    path.write_text(yaml.safe_dump({"services": services}), encoding="utf-8")
    return path


def test_industrial_bundle_only_qualifies_selected_python_images(tmp_path):
    server = f"simplephysx/spx-server:{images.SPX_SERVER_VERSION}"
    path = write_compose(
        tmp_path,
        **{
            "spx-server": {"image": server},
            "mqtt_broker": {"image": "eclipse-mosquitto:latest"},
        },
    )
    assert images.compose_python_images(path) == [server]


def test_selected_optional_providers_are_included_with_pinned_digests(tmp_path):
    server = f"simplephysx/spx-server:{images.SPX_SERVER_VERSION}"
    matter = "ghcr.io/home-assistant-libs/python-matter-server@sha256:" + "a" * 64
    homeassistant = "ghcr.io/home-assistant/home-assistant:stable"
    path = write_compose(
        tmp_path,
        **{
            "spx-server": {"image": server},
            "matter_server": {"image": matter},
            "homeassistant_bridge": {"image": homeassistant},
        },
    )
    assert images.compose_python_images(path) == sorted([server, matter, homeassistant])


def test_compose_without_spx_server_cannot_pass_an_empty_gate(tmp_path):
    path = write_compose(tmp_path, mqtt_broker={"image": "eclipse-mosquitto:latest"})
    with pytest.raises(ValueError, match="must include the SPX Server image"):
        images.compose_python_images(path)


def test_selected_vulnerable_matter_fails_the_compose_gate(tmp_path, monkeypatch):
    matter = "ghcr.io/home-assistant-libs/python-matter-server:stable"
    path = write_compose(
        tmp_path,
        **{
            "spx-server": {"image": f"simplephysx/spx-server:{images.SPX_SERVER_VERSION}"},
            "matter_server": {"image": matter},
        },
    )

    def verify(image, **kwargs):
        if image == matter:
            images.validate_versions({"certifi": "2026.7.22"})
        return [{"certifi": "2026.10.23"}]

    monkeypatch.setattr(images, "verify_image", verify)
    monkeypatch.setattr("sys.argv", ["verify_python_images", "--compose", str(path)])
    with pytest.raises(RuntimeError, match="Unsafe image package certifi"):
        images.main()


@pytest.mark.parametrize(
    "package,version",
    [
        ("pip", "26.0.1"),
        ("certifi", "2026.7.22"),
        ("uv", "0.12.23"),
    ],
)
def test_image_gate_rejects_installed_vulnerable_packages(package, version):
    with pytest.raises(RuntimeError, match="Unsafe image package"):
        images.validate_versions({package: version})


def test_image_gate_allows_absent_optional_tools():
    images.validate_versions({"certifi": "2026.10.23"})


def test_verification_checks_both_interpreters_without_repairing_image(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(
            returncode=0, stdout='{"pip":"26.2.2","certifi":"2026.10.23"}'
        )

    monkeypatch.setattr(images.subprocess, "run", run)
    assert len(images.verify_image("reviewed-image", pull=False)) == 2
    assert [argv[argv.index("--entrypoint") + 1] for argv in calls] == [
        "python",
        "/usr/local/bin/python",
    ]
    assert all("install" not in argv and "none" in argv for argv in calls)
