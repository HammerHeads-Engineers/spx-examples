"""Explicit presentation selection, independent of runtime workspace modes."""

from . import terminal_selection


def agent_setup_available() -> bool:
    # Expose the menu entry only when the complete agent implementation ships.
    from importlib.util import find_spec

    return find_spec("installer.setup_workspace") is not None


def choose_wizard_mode(explicit=None) -> str:
    if explicit is not None:
        if explicit == "agent" and not agent_setup_available():
            raise SystemExit("Agent Setup is not included in this installer yet.")
        return explicit
    if not terminal_selection.is_interactive():
        print("[spx-installer] Interactive controls unavailable; using legacy mode.")
        return "legacy"
    modes = ["interactive", "legacy"]
    labels = ["Interactive (default)", "Legacy (text prompts)"]
    if agent_setup_available():
        modes.append("agent")
        labels.append("Configure with your own agent")
    selected = terminal_selection.select_one(
        "How would you like to configure SPX?", labels
    )
    if selected is None:
        return "legacy"
    if selected.shortcut == "q":
        raise SystemExit(0)
    return modes[selected.indices[0] - 1]
