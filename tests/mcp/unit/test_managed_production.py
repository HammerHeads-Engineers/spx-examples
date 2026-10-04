# SPDX-License-Identifier: MIT
"""Managed configuration and explicit server diagnostics regressions."""

import json
from urllib.error import HTTPError, URLError

import pytest

from spx_mcp import cli
from spx_mcp.config import SpxMcpConfig


def test_managed_workspace_ignores_inherited_key_and_url(tmp_path, monkeypatch):
    (tmp_path / '.spx-mcp-workspace.json').write_text(json.dumps({
        'kind': 'spx-mcp-workspace', 'workspace_kind': 'managed'}))
    (tmp_path / '.env').write_text('SPX_PRODUCT_KEY=current-key\nSPX_BASE_URL=http://current:8000\n')
    monkeypatch.setenv('SPX_PRODUCT_KEY', 'stale-host-key')
    monkeypatch.setenv('SPX_BASE_URL', 'http://stale:8000')
    config = SpxMcpConfig.from_sources(repo_root=str(tmp_path))
    assert config.product_key == 'current-key'
    assert config.spx_base_url == 'http://current:8000'


@pytest.mark.parametrize('error', [HTTPError('http://server', 401, 'Unauthorized', {}, None),
                                  HTTPError('http://server', 403, 'Forbidden', {}, None),
                                  URLError('offline')])
def test_live_doctor_rejects_authentication_and_connection_failures(tmp_path, monkeypatch, error):
    catalog = tmp_path / 'library/catalog'
    catalog.mkdir(parents=True)
    (catalog / 'models.yaml').write_text('models: []')
    monkeypatch.setattr(cli, 'find_spec', lambda name: True)
    monkeypatch.setattr(cli, 'runtime_backend_report', lambda: {
        'ok': True, 'spx_python_available': True, 'spx_python_importable': True,
        'checks': [], 'problems': []})
    config = SpxMcpConfig.from_sources(repo_root=str(tmp_path), product_key='private-test-key')

    def fail(request, *, timeout):
        assert request.headers['Authorization'] == 'Bearer private-test-key'
        assert timeout <= 5
        raise error

    monkeypatch.setattr(cli, 'urlopen', fail, raising=False)
    report = cli.doctor_report(config, check_server=True)
    assert report['ok'] is False
    assert report['server_check']['checked'] is True
    assert report['server_check']['ok'] is False
    assert 'private-test-key' not in json.dumps(report)


def test_offline_doctor_explicitly_reports_no_server_verification(tmp_path):
    report = cli.doctor_report(SpxMcpConfig.from_sources(repo_root=str(tmp_path)))
    assert report['server_check']['checked'] is False
