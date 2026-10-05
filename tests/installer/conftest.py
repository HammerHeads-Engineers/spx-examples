"""Keep unit installer transactions away from real user workspaces/downloads."""

import pytest


@pytest.fixture(autouse=True)
def isolated_tool_preparation(monkeypatch, tmp_path):
    from installer.setup_session import SetupEngine

    monkeypatch.setattr(
        SetupEngine,
        "_prepare_tools",
        lambda self, session, *, started: {
            "ok": True,
            "workspace": str(tmp_path / "tools"),
            "server_checked": started,
            "server_name": "spx",
        },
    )
