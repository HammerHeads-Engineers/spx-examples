# SPDX-License-Identifier: MIT
"""Secret-safe product-key format checks shared by Setup and generated bundles."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys


_KEY_PATTERN = re.compile(r"(?:[A-Z2-7]{30}|(?:[A-Z2-7]{5}-){5}[A-Z2-7]{5})")
FORMAT_GUIDANCE = (
    "Invalid SPX product key format. Expected 30 uppercase characters (A-Z or 2-7), "
    "either without dashes or in six groups: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX. "
    "Run SPX Setup and enter the complete product key."
)


def validate_product_key_format(value: str) -> str:
    """Check structure only; authenticity and entitlement belong to the server."""
    if not _KEY_PATTERN.fullmatch(value):
        raise ValueError(FORMAT_GUIDANCE)
    return value


def runtime_product_key(env_file: Path) -> str:
    """Match Compose precedence: a process variable (even empty) overrides .env."""
    if "SPX_PRODUCT_KEY" in os.environ:
        return os.environ["SPX_PRODUCT_KEY"]
    value = ""
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        name, separator, raw = line.partition("=")
        if not separator or name.strip() != "SPX_PRODUCT_KEY":
            continue
        raw = raw.strip()
        if raw.startswith(("'", '"')):
            # Product keys contain no escapes or expansions. Only accept an
            # entire quoted value, optionally followed by a comment.
            quoted = re.fullmatch(r"(['\"])([A-Z2-7-]*)\1(?:\s*#.*)?", raw)
            value = quoted.group(2) if quoted else raw
        else:
            # In Compose an unquoted inline comment requires preceding space.
            value = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the SPX product key before starting Docker"
    )
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate_product_key_format(runtime_product_key(args.env_file))
    except (ValueError, OSError, UnicodeError):
        print(f"[spx-preflight] {FORMAT_GUIDANCE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
