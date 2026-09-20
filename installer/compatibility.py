# SPDX-License-Identifier: MIT
"""Explicit compatibility contract for the installer runtime images."""

from __future__ import annotations

SPX_SERVER_VERSION = "v1.0.0-rc.64"
SPX_UI_VERSION = "v1.0.0-rc.68"

# Keep this table explicit.  A future image bump must be reviewed as a pair,
# rather than silently producing a bundle with an unsupported combination.
SUPPORTED_VERSION_PAIRS = {
    (SPX_SERVER_VERSION, SPX_UI_VERSION),
}


def validate_version_pair(server_version: str, ui_version: str) -> None:
    if (server_version, ui_version) not in SUPPORTED_VERSION_PAIRS:
        supported = ", ".join(f"{server}/{ui}" for server, ui in sorted(SUPPORTED_VERSION_PAIRS))
        raise ValueError(
            f"Unsupported SPX Server/UI version pair: {server_version}/{ui_version}. "
            f"Supported pair(s): {supported}"
        )
