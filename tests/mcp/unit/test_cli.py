# SPDX-License-Identifier: MIT

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
    assert "SPX_PRODUCT_KEY is not set." in captured.out
