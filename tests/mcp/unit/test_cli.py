# SPDX-License-Identifier: MIT

import json
from pathlib import Path

from spx_mcp import cli


def test_list_tools_excludes_write_tools_by_default(capsys) -> None:
    rc = cli.main(["list-tools"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "repo_list_model_scenarios" in captured.out
    assert "repo_get_model_scenario" in captured.out
    assert "server_list_scenarios" in captured.out
    assert "server_get_scenario" in captured.out
    assert "repo_upsert_model_scenario" not in captured.out
    assert "repo_delete_model_scenario" not in captured.out
    assert "server_set_attr" not in captured.out
    assert "server_set_attrs" not in captured.out
    assert "server_ramp_attr" not in captured.out
    assert "server_register_model_and_ensure_instance" not in captured.out
    assert "server_upsert_scenario" not in captured.out
    assert "server_start_scenario" not in captured.out
    assert "server_stop_scenario" not in captured.out
    assert "server_delete_scenario" not in captured.out
    assert "server_get_attrs" in captured.out
    assert "repo_list_packs" in captured.out


def test_list_tools_includes_write_tools_when_enabled(capsys) -> None:
    rc = cli.main(["list-tools", "--allow-write"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "repo_upsert_model_scenario" in captured.out
    assert "repo_delete_model_scenario" in captured.out
    assert "server_register_model_and_ensure_instance" in captured.out
    assert "server_set_attr" in captured.out
    assert "server_set_attrs" in captured.out
    assert "server_ramp_attr" in captured.out
    assert "server_upsert_scenario" in captured.out
    assert "server_start_scenario" in captured.out
    assert "server_stop_scenario" in captured.out
    assert "server_delete_scenario" in captured.out


def test_doctor_fails_when_runtime_prerequisites_are_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)

    rc = cli.main(["doctor", "--repo-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "SPX_PRODUCT_KEY is missing or invalid for this MCP workspace." in captured.out
    assert "workspace .env" in captured.out


def test_doctor_reports_runtime_backend_status(tmp_path: Path, monkeypatch) -> None:
    catalog_dir = tmp_path / "library" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "models.yaml").write_text("models: []\n", encoding="utf-8")
    original_find_spec = cli.find_spec

    monkeypatch.setattr(
        cli,
        "find_spec",
        lambda name: object() if name == "mcp" else original_find_spec(name),
    )
    monkeypatch.setattr(cli, "python_supports_mcp", lambda: True)

    monkeypatch.setattr(
        cli,
        "runtime_backend_report",
        lambda: {
            "ok": True,
            "checks": [
                "local model definitions load from YAML/JSON without spx_python.helpers",
                "instance bootstrap uses direct client registry access without spx_python.helpers",
            ],
            "problems": [],
            "spx_python_available": True,
            "spx_python_importable": True,
        },
    )

    report = cli.doctor_report(
        cli.SpxMcpConfig.from_sources(
            repo_root=str(tmp_path),
            product_key="TEST-CLI-KEY",
            allow_write=True,
        )
    )

    assert report["ok"] is True
    assert report["runtime_backend_usable"] is True
    assert report["spx_python_available"] is True
    assert report["spx_python_importable"] is True
    assert any("without spx_python.helpers" in check for check in report["runtime_backend_checks"])


def test_doctor_json_reports_runtime_backend_failures(tmp_path: Path, monkeypatch, capsys) -> None:
    catalog_dir = tmp_path / "library" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "models.yaml").write_text("models: []\n", encoding="utf-8")
    original_find_spec = cli.find_spec

    monkeypatch.setattr(
        cli,
        "find_spec",
        lambda name: object() if name == "mcp" else original_find_spec(name),
    )
    monkeypatch.setattr(cli, "python_supports_mcp", lambda: True)

    monkeypatch.setattr(
        cli,
        "runtime_backend_report",
        lambda: {
            "ok": False,
            "checks": ["spx_python and spx_python.client import successfully"],
            "problems": ["The MCP runtime bootstrap path is not importable: RuntimeError: broken"],
            "spx_python_available": True,
            "spx_python_importable": True,
        },
    )

    rc = cli.main(
        [
            "doctor",
            "--repo-root",
            str(tmp_path),
            "--product-key",
            "TEST-CLI-KEY",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert rc == 1
    assert report["runtime_backend_usable"] is False
    assert report["problems"] == [
        "The MCP runtime bootstrap path is not importable: RuntimeError: broken"
    ]
