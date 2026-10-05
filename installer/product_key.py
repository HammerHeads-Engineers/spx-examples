# SPDX-License-Identifier: MIT
"""Secret-safe product-key format checks shared by Setup and generated bundles."""

from __future__ import annotations

import argparse
import binascii
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


def product_key_summary(value: str) -> dict:
    """Public planning hints, never authentication or personal key fields.

    The shipped key layout is shared with spx_server.limits. A checksum-valid
    key carries its instance budget after the two-character plan identifier.
    Community's CO prefix also gives a conservative five-instance planning cap.
    The running server remains responsible for license validity and expiry.
    """
    result = {"plan": "Unknown", "instance_limit": None, "server_verified": False}
    try:
        compact = validate_product_key_format(value).replace("-", "")
    except ValueError:
        return result
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = "".join(f"{alphabet.index(c):05b}" for c in compact)
    checksum_valid = binascii.crc_hqx(
        int(bits[:118] + "00", 2).to_bytes(15, "big"), 0xFFFF
    ) == int(bits[118:134], 2)
    community = compact.startswith("CO")
    if checksum_valid:
        limit = int(bits[10:18], 2)
        result.update(
            plan="Community" if community else compact[:2],
            instance_limit=min(limit, 5) if community else limit,
            source="embedded_fields",
        )
    elif community:
        result.update(plan="Community", instance_limit=5, source="community_prefix")
    return result


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
