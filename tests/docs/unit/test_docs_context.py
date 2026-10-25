import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import sync_docs_context as sync


def commit(repo, message):
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Docs test', '-c', 'user.email=docs-test@example.invalid', 'commit', '-qm', message], check=True)
    return sync.git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def source(tmp_path, monkeypatch):
    repo = tmp_path / 'source'
    repo.mkdir()
    subprocess.run(['git', 'init', str(repo)], check=True, capture_output=True)
    for path in sync.PAGES:
        f = repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('# Complete reference\n\nContent for offline use.\n')
    sha = commit(repo, 'source')
    destination = tmp_path / 'destination'
    (destination / 'docs').mkdir(parents=True)
    monkeypatch.setattr(sync, 'ROOT', destination)
    return repo, sha, destination


def test_export_is_complete_and_drift_fails(source):
    repo, sha, destination = source
    sync.synchronize(repo, sha)
    sync.synchronize(repo, sha, check=True)
    for path in sync.PAGES:
        text = (destination / sync.PAGES[path][0]).read_text()
        assert sha in text and 'Content for offline use.' in text
    (destination / 'docs/MCP.md').write_text('manual edit')
    with pytest.raises(ValueError, match='drift'):
        sync.synchronize(repo, sha, check=True)


def test_unrelated_commit_keeps_pin_and_files_unchanged(source):
    repo, sha, destination = source
    sync.synchronize(repo, sha)
    before = {p: p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    (repo / 'unrelated.md').write_text('Not an export input\n')
    newer = commit(repo, 'unrelated')
    assert newer != sha
    assert sync.synchronize(repo, newer, update=True) is False
    assert before == {p: p.read_bytes() for p in before}
    assert json.loads((destination / 'docs-source.json').read_text())['commit'] == sha


def test_missing_revision_never_uses_head(source):
    repo, _, _ = source
    with pytest.raises(subprocess.CalledProcessError):
        sync.source_pages(repo, 'f' * 40)
    with pytest.raises(ValueError, match='full Docs commit'):
        sync.source_pages(repo, 'main')


def test_portability_is_required(source):
    repo, _, _ = source
    path = repo / next(iter(sync.PAGES))
    path.write_text('# Reference\n\n[Unavailable offline](../other.md)\n')
    sha = commit(repo, 'nonportable')
    with pytest.raises(ValueError, match='portable Markdown'):
        sync.source_pages(repo, sha)


def test_readme_model_matches_canonical_snapshot():
    readme = (ROOT / 'README.md').read_text()
    reference = (ROOT / 'docs/MODEL_LANGUAGE.md').read_text()
    load = lambda text: yaml.safe_load(re.search(r'```yaml\n(.*?)\n```', text, re.S).group(1))
    assert load(readme) == load(reference)
    jsn = json.loads(re.search(r'```json\n(.*?)\n```', reference, re.S).group(1))
    assert jsn == load(readme)
