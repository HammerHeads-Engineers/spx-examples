# SPDX-License-Identifier: MIT

from pathlib import Path

from spx_mcp.backend.models import validate_model_path


def test_validate_model_path_reports_missing_attributes(tmp_path: Path) -> None:
    model_path = tmp_path / "broken_model.yaml"
    model_path.write_text("name: broken_model\n", encoding="utf-8")

    result = validate_model_path(model_path)

    assert result["ok"] is False
    assert any("attributes" in error for error in result["errors"])
