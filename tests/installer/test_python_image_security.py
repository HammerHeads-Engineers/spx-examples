# SPDX-License-Identifier: MIT
import pytest
from types import SimpleNamespace

from tools import verify_python_images as images


def test_catalog_includes_all_shipped_python_providers():
    shipped = images.shipped_images()
    assert any("spx-server" in image for image in shipped)
    assert any("home-assistant/home-assistant" in image for image in shipped)
    assert any("python-matter-server" in image for image in shipped)


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
