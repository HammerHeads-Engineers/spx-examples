#!/usr/bin/env python3
"""Export complete offline model/MCP references from an exact public Docs commit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'HammerHeads-Engineers/spx-docs'
PAGES = {
    'simulation-and-modeling/model-definition-reference.md': ('docs/MODEL_LANGUAGE.md', 'https://docs.simplephysx.com/reference/model-definition-reference'),
    'getting-started/mcp-reference.md': ('docs/MCP.md', 'https://docs.simplephysx.com/reference/mcp-reference'),
}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def source_pages(repo, sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('A full Docs commit SHA is required')
    resolved = git(repo, 'rev-parse', '--verify', sha + '^{commit}')
    if resolved != sha:
        raise ValueError('Docs revision does not resolve to the pinned commit')
    result = {}
    for source, (target, url) in PAGES.items():
        text = subprocess.check_output(['git', '-C', str(repo), 'show', f'{sha}:{source}'], text=True)
        if '{%' in text or '../' in '\n'.join(re.findall(r'\]\(([^)]+)\)', text)):
            raise ValueError(f'{source}: export pages must use portable Markdown and absolute links')
        result[source] = text
    return result


def digest(pages):
    return hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()


def render(source, text, sha):
    target, url = PAGES[source]
    return f'<!-- Generated from {REPOSITORY}@{sha}:{source}; do not edit. -->\n\n' + f'> Canonical reference: [{url}]({url})\n> Source commit: `{sha}`. This complete offline snapshot follows the release baseline in spx-docs/sources.json.\n\n' + text


def synchronize(repo, sha, check=False, update=False):
    path = ROOT / 'docs-source.json'
    manifest = json.loads(path.read_text()) if path.exists() else {}
    pages = source_pages(repo, sha)
    content_hash = digest(pages)
    if update and manifest.get('content_sha256') == content_hash:
        print('No canonical model/MCP content changes; leaving source pin untouched.')
        return False
    expected = {'schema_version': 1, 'repository': REPOSITORY, 'commit': sha,
                'content_sha256': content_hash,
                'exports': {s: {'path': t, 'canonical_url': u} for s, (t, u) in PAGES.items()}}
    mismatches = []
    for source, text in pages.items():
        output = ROOT / PAGES[source][0]
        rendered = render(source, text, sha)
        if check:
            if not output.exists() or output.read_text() != rendered:
                mismatches.append(str(output.relative_to(ROOT)))
        else:
            output.write_text(rendered)
    if check:
        if manifest != expected:
            mismatches.append('docs-source.json')
        if mismatches:
            raise ValueError('Offline documentation drift: ' + ', '.join(mismatches))
        print('Offline context and provenance match the pinned Docs input.')
    else:
        path.write_text(json.dumps(expected, indent=2) + '\n')
        print('Exported complete model and MCP references.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docs-root', type=Path)
    parser.add_argument('--commit')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()
    if args.check and args.update:
        parser.error('--check and --update are mutually exclusive')
    manifest_path = ROOT / 'docs-source.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest and manifest.get('repository') != REPOSITORY:
        raise ValueError('Only the canonical public Docs repository is allowed')
    sha = args.commit or manifest.get('commit')
    if args.update:
        sha = subprocess.check_output(['git', 'ls-remote', 'https://github.com/' + REPOSITORY + '.git', 'refs/heads/main'], text=True).split()[0]
    if not sha or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Missing or invalid pinned Docs commit')
    if args.docs_root:
        synchronize(args.docs_root, sha, args.check, args.update)
        return
    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary) / 'docs'
        subprocess.run(['git', 'init', str(repo)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repo), 'fetch', '--depth=1', 'https://github.com/' + REPOSITORY + '.git', sha], check=True)
        synchronize(repo, sha, args.check, args.update)


if __name__ == '__main__':
    main()
