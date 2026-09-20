# SPDX-License-Identifier: MIT
"""Runtime object shared across MCP tool registrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import SpxMcpConfig
from .errors import WriteAccessError
from .backend.catalog import RepoCatalog
from .backend.client import create_spx_client


@dataclass
class SpxMcpRuntime:
    """Shared runtime services for the local MCP server."""

    config: SpxMcpConfig
    _catalog: Optional[RepoCatalog] = field(default=None, init=False, repr=False)

    @property
    def catalog(self) -> RepoCatalog:
        if self._catalog is None:
            self._catalog = RepoCatalog(self.config.repo_root)
        return self._catalog

    def create_client(self):
        return create_spx_client(self.config)

    def require_write(self) -> None:
        if not self.config.allow_write:
            raise WriteAccessError(
                "Write tools are disabled. Restart spx-mcp with --allow-write to enable mutations."
            )
