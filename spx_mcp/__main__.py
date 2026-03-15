# SPDX-License-Identifier: MIT
"""Module entrypoint for `python -m spx_mcp`."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
