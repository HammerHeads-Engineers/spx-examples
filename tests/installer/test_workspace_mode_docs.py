# SPDX-License-Identifier: MIT
"""Content guards for workspace mode documentation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_readme_describes_work_modes_for_end_users() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Work Modes" in readme
    assert "Use this mode when:" in readme
    assert "installer-managed workspaces are created as `runtime_mcp`" in readme
    assert "manual repo clones still default to `repo_dev` even if MCP is available" in readme
    assert "Do not guess `runtime_mcp` only because MCP is installed" in readme
    assert "Protocol smoke tests are not part of that default success path." in readme
    assert "write-enabled by default" in readme


def test_agents_defines_runtime_only_instance_and_diagnostic_policy() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "## Mode Resolution" in agents
    assert "#### `runtime_mcp` instance work" in agents
    assert "#### `runtime_mcp` diagnostics and scenario flows" in agents
    assert "runtime changes are ephemeral unless the user explicitly asks to persist them back into the repository" in agents
    assert "prefer MCP `server_*` tools for register, ensure, recreate, start, stop, reset, and live validation flows" in agents
    assert "protocol smoke tests such as Modbus/MQTT/OPC UA read-write checks are opt-in or failure-driven" in agents


def test_mcp_docs_align_runtime_and_repo_workflows() -> None:
    mcp_doc = (REPO_ROOT / "docs" / "MCP.md").read_text(encoding="utf-8")

    assert "## Runtime-first MCP workflow" in mcp_doc
    assert "## Repository development workflow" in mcp_doc
    assert "`server_*` tools are the default path" in mcp_doc
    assert "`repo_dev` remains the default for ordinary manual clones" in mcp_doc
    assert "Protocol smoke tests are opt-in or failure-driven in `runtime_mcp`." in mcp_doc
    assert "read/write mode by default" in mcp_doc
