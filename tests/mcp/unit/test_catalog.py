# SPDX-License-Identifier: MIT

from pathlib import Path

from spx_mcp.backend.catalog import RepoCatalog


def test_repo_catalog_lists_packs_profiles_and_models(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "library" / "catalog"
    profiles_dir = tmp_path / "profiles" / "test_pack"
    domains_dir = tmp_path / "library" / "domains" / "environment" / "sensor" / "generic"
    catalog_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    domains_dir.mkdir(parents=True)

    (domains_dir / "sensor.yaml").write_text(
        "name: sensor\nattributes:\n  temperature: 20\n",
        encoding="utf-8",
    )
    (catalog_dir / "domains.yaml").write_text(
        "domains:\n  - id: environment\n    name: Environment\n    description: Env\n    path: library/domains/environment\n",
        encoding="utf-8",
    )
    (catalog_dir / "services.yaml").write_text(
        "services: []\n",
        encoding="utf-8",
    )
    (catalog_dir / "industries.yaml").write_text(
        "industries:\n  - id: test_pack\n    name: Test Pack\n    description: Example\n    protocols: [mqtt]\n    services: []\n    profiles:\n      - profiles/test_pack/test_profile.yaml\n    path: library/industries/test_pack\n",
        encoding="utf-8",
    )
    (catalog_dir / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "  - id: sensor",
                "    name: sensor",
                "    path: library/domains/environment/sensor/generic/sensor.yaml",
                "    domain: environment",
                "    domain_group: environment",
                "    device_class: sensor",
                "    vendor: generic",
                "    protocols: [mqtt]",
                "    services: []",
                "    packages: [test_pack]",
                "    profiles: [test_profile]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (profiles_dir / "test_profile.yaml").write_text(
        "name: test_profile\ndescription: Example profile\nmodels:\n  - library/domains/environment/sensor/generic/sensor.yaml\nservices: []\n",
        encoding="utf-8",
    )

    catalog = RepoCatalog(tmp_path)

    assert catalog.list_packs()[0]["id"] == "test_pack"
    assert catalog.list_profiles()[0]["id"] == "test_profile"
    assert catalog.find_models(query="sensor")[0]["id"] == "sensor"
    assert catalog.get_model_path("sensor") == domains_dir / "sensor.yaml"
