# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Optional

import pytest

from installer import cli


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


def _selection(*, install_spx_ui: bool = True) -> SimpleNamespace:
    return SimpleNamespace(install_spx_ui=install_spx_ui)


def _enable_interactive_session(monkeypatch: pytest.MonkeyPatch) -> _TtyStream:
    stream = _TtyStream()
    monkeypatch.setattr(cli.sys, "stdin", _TtyStream())
    return stream


def test_open_ui_browser_after_successful_interactive_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _enable_interactive_session(monkeypatch)
    opened: list[tuple[str, int]] = []
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("SPX_OPEN_BROWSER", raising=False)
    monkeypatch.setattr(
        cli.webbrowser,
        "open",
        lambda url, new=0: opened.append((url, new)) or True,
    )

    cli._open_ui_browser(_selection(), stream=stream)

    assert opened == [(cli.SPX_UI_URL, 2)]
    assert cli.SPX_UI_URL in stream.getvalue()


@pytest.mark.parametrize(
    "selection,env_name,env_value",
    [
        (_selection(install_spx_ui=False), None, None),
        (_selection(), "SPX_OPEN_BROWSER", "0"),
        (_selection(), "CI", "1"),
    ],
)
def test_open_ui_browser_skips_non_applicable_sessions(
    monkeypatch: pytest.MonkeyPatch,
    selection: SimpleNamespace,
    env_name: Optional[str],
    env_value: Optional[str],
) -> None:
    stream = _enable_interactive_session(monkeypatch)
    opened: list[str] = []
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("SPX_OPEN_BROWSER", raising=False)
    if env_name is not None and env_value is not None:
        monkeypatch.setenv(env_name, env_value)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url, new=0: opened.append(url))

    cli._open_ui_browser(selection, stream=stream)

    assert opened == []


def test_open_ui_browser_skips_headless_session(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _TtyStream()
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO())
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        cli.webbrowser,
        "open",
        lambda *args, **kwargs: pytest.fail("browser must not open headlessly"),
    )

    cli._open_ui_browser(_selection(), stream=stream)


def test_open_ui_browser_failure_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _enable_interactive_session(monkeypatch)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    def fail_open(*args, **kwargs):
        raise OSError("no browser available")

    monkeypatch.setattr(cli.webbrowser, "open", fail_open)

    cli._open_ui_browser(_selection(), stream=stream)

    assert "Could not open" in stream.getvalue()
