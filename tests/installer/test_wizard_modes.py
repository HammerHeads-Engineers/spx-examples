import pytest

from installer import cli, terminal_selection
from installer.wizard import InstallerWizard


def test_explicit_legacy_never_uses_raw_key_selectors(monkeypatch):
    wizard = InstallerWizard(mode="legacy")
    monkeypatch.setattr(
        terminal_selection, "select_one", lambda *a, **k: pytest.fail("raw selector")
    )
    monkeypatch.setattr("builtins.input", lambda _: "2")
    assert wizard._prompt_indices("Choose: ", 2, allow_empty=False) == [2]


def test_interactive_falls_back_with_explanation(monkeypatch, capsys):
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: False)
    wizard = InstallerWizard(mode="interactive")
    assert wizard.mode == "legacy"
    assert "legacy" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("mode", ["interactive", "legacy", "agent"])
def test_cli_accepts_explicit_modes(mode):
    args = cli.build_parser().parse_args(
        ["generate", "--wizard-mode", mode, "--no-start"]
    )
    assert args.wizard_mode == mode


def test_interactive_package_list_is_not_printed_twice(monkeypatch, capsys):
    from installer.manifest import ManifestLoader

    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(
        terminal_selection,
        "select_many",
        lambda *a, **k: terminal_selection.SelectionResult([1]),
    )
    wizard = InstallerWizard(mode="interactive")
    index = ManifestLoader().load()
    wizard._prompt_packages(index.industries, index)
    assert "Available packages:" not in capsys.readouterr().out
