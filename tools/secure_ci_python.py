# SPDX-License-Identifier: MIT
"""Prepare a secure CI toolchain and dependency environment before Poetry runs."""

from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.runtime_bootstrap import ensure_runtime, verify_environment  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    python = ensure_runtime(root / ".spx-ci", ["poetry==2.2.1"])
    dependency_python = ensure_runtime(root / ".venv", [])
    verify_environment(python)
    # Subsequent steps, including `poetry install`, use this exact environment.
    if "GITHUB_PATH" in os.environ:
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as handle:
            handle.write(str(python.parent) + "\n")
    if "GITHUB_ENV" in os.environ:
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
            handle.write("VIRTUAL_ENV=" + str(dependency_python.parent.parent) + "\n")
    print(f"Secure CI Python: {python}")


if __name__ == "__main__":
    main()
