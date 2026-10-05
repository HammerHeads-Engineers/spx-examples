"""Keep unit installer transactions away from real user workspaces/downloads."""

import importlib.util

import pytest


@pytest.fixture(autouse=True)
def isolated_tool_preparation(monkeypatch, tmp_path):
    # Standalone shell/preflight smoke jobs install only pytest. They never
    # use SetupEngine and must not acquire its YAML/runtime dependencies here.
    if importlib.util.find_spec("yaml") is None:
        return
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
