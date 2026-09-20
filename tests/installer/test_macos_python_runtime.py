# SPDX-License-Identifier: MIT

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mac_shell_launchers_source_and_prefer_packaged_python() -> None:
    helper = (REPO_ROOT / "installer/macos/python_runtime.sh").read_text(
        encoding="utf-8"
    )
    install_script = (REPO_ROOT / "spx-install.sh").read_text(encoding="utf-8")
    mcp_script = (REPO_ROOT / "spx-mcp-setup.sh").read_text(encoding="utf-8")

    assert 'SPX_MACOS_PYTHON_VERSION="${SPX_MACOS_PYTHON_VERSION:-3.12.10}"' in helper
    assert "/Library/Frameworks/Python.framework/Versions/" in helper
    assert (
        '"/Library/Frameworks/Python.framework/Versions/Current/bin/"python3.*'
        in helper
    )
    assert "installer/macos/python_runtime.sh" in install_script
    assert "spx_resolve_macos_python" in install_script
    assert "installer/macos/python_runtime.sh" in mcp_script
    assert 'candidates+=("${resolved}")' in mcp_script
    assert "SPX_MACOS_BUNDLED_ONLY" in helper
    assert ".spx-macos-bundled-python" in mcp_script
    assert "Portable archives deliberately keep" in mcp_script
