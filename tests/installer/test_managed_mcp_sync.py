# SPDX-License-Identifier: MIT
"""Installer commit updates only an existing managed MCP workspace."""

import json

import pytest

from installer import mcp_workspace as mw


def test_explicit_managed_seed_has_priority_over_host_environment():
    assert mw.merge_workspace_seed_env(
        {'SPX_PRODUCT_KEY': 'new-key', 'SPX_BASE_URL': 'http://new:8000'},
        {'SPX_PRODUCT_KEY': 'old-key', 'SPX_BASE_URL': 'http://old:8000'},
        workspace_kind='managed', explicit_seed=True,
    )['SPX_PRODUCT_KEY'] == 'new-key'
    assert mw.merge_workspace_seed_env(
        {'SPX_PRODUCT_KEY': 'new-key'}, {'SPX_PRODUCT_KEY': 'old-key'},
        workspace_kind='git', explicit_seed=True,
    )['SPX_PRODUCT_KEY'] == 'old-key'


def test_atomic_env_failure_preserves_previous_configuration(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('SPX_PRODUCT_KEY=old-key\nCUSTOM=retained\n')
    before = path.read_bytes()

    def fail(*args):
        raise OSError('replace failed')

    monkeypatch.setattr(mw.os, 'replace', fail)
    with pytest.raises(OSError):
        mw.write_dotenv(path, {'SPX_PRODUCT_KEY': 'new-key'})
    assert path.read_bytes() == before


def test_sync_managed_workspace_uses_committed_seed_and_preserves_settings(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    (workspace / mw.WORKSPACE_MARKER_NAME).write_text(json.dumps({
        'kind': mw.WORKSPACE_MARKER_KIND, 'workspace_kind': 'managed',
        'source_root': str(source), 'server_name': 'spx', 'allow_write': True}))
    (workspace / '.env').write_text('SPX_PRODUCT_KEY=old-key\nCUSTOM=retained\n')
    seed = tmp_path / 'committed.env'
    seed.write_text('SPX_PRODUCT_KEY=new-key\nSPX_BASE_URL=http://new:8000\n')
    calls = []
    monkeypatch.setattr(mw, 'validate_source_root', lambda root: None)
    monkeypatch.setattr(mw, 'sync_payload', lambda *args: None)
    monkeypatch.setattr(mw, 'bootstrap_codex', lambda *args, **kwargs: calls.append(('codex', args)))
    monkeypatch.setattr(mw, 'write_claude_mcp_config', lambda *args, **kwargs: calls.append(('claude', args)))
    assert mw.synchronize_managed_workspace(seed, workspace_dir=workspace)
    assert mw.read_dotenv(workspace / '.env') == {
        'CUSTOM': 'retained', 'SPX_PRODUCT_KEY': 'new-key', 'SPX_BASE_URL': 'http://new:8000',
        **{key: value for key, value in mw.build_workspace_env(existing={}, seeded={}).items()
           if key not in {'SPX_PRODUCT_KEY', 'SPX_BASE_URL'}},
    }
    assert len(calls) == 2


def test_sync_does_not_create_workspace_or_modify_git_checkout(tmp_path):
    assert mw.synchronize_managed_workspace(tmp_path / 'seed.env', workspace_dir=tmp_path / 'absent') is False
    (tmp_path / '.git').mkdir()
    assert mw.synchronize_managed_workspace(tmp_path / 'seed.env', workspace_dir=tmp_path) is False
