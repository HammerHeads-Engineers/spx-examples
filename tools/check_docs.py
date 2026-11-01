"""Check portable local doc targets, repository Python commands and marked models.

No network, credentials or live server are used. External URLs, Markdown anchors,
notebooks and the runtime behavior of examples remain separate review/execution.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit

import yaml

from tools.validate_models import ValidationResult, validate_model_file

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = "<!-- documentation-status: historical -->"
MODEL_MARKER = "<!-- spx-model-example -->"
MODEL_BLOCK = re.compile(re.escape(MODEL_MARKER) + r"\s*```yaml\s*\n(.*?)\n```", re.S)
FENCES = re.compile(r"```[^\n]*\n.*?```", re.S)
LINKS = re.compile(r"\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
REFERENCES = re.compile(r"^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.M)
MODULES = re.compile(
    r"\bpython(?:\.exe)?\s+-m\s+((?:tools|scripts|spx_mcp|installer)(?:\.[\w]+)*)\b"
)
SCRIPTS = re.compile(
    r"\bpython(?:\.exe)?\s+((?:tools|scripts|examples)/[\w./-]+\.py)\b"
)


def document_paths(root):
    paths = [
        root / name
        for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "CLAUDE.md")
    ]
    for directory in ("docs", "examples", "library/industries", ".github"):
        paths.extend((root / directory).rglob("*.md"))
    return sorted(path for path in set(paths) if path.is_file())


def _local_target_issue(root, document, href):
    parsed = urlsplit(href.strip("<>"))
    if parsed.scheme or href.startswith("//") or not parsed.path:
        return None
    relative = PurePosixPath(
        posixpath.normpath(
            (document.parent.relative_to(root).as_posix() + "/" + unquote(parsed.path))
        )
    )
    if parsed.path.startswith("/") or relative.is_absolute() or ".." in relative.parts:
        return "local link must stay inside the repository: " + href
    target = root
    for part in relative.parts:
        if not target.is_dir() or part not in {
            entry.name for entry in target.iterdir()
        }:
            return "missing or incorrectly cased local link: " + href
        target = target / part
    return None


def check_docs(root=ROOT):
    root = root.resolve()
    issues = []
    for path in document_paths(root):
        label = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        prose = FENCES.sub("", text)
        for pattern in (LINKS, REFERENCES):
            for match in pattern.finditer(prose):
                try:
                    issue = _local_target_issue(root, path, match.group(1))
                except ValueError:
                    issue = "invalid link target: " + match.group(1)
                if issue:
                    issues.append(f"{label}: {issue}")
        # Pinned product snapshots are verified by docs-sync. Historical reports
        # preserve old commands as evidence, not current operating instructions.
        if HISTORICAL in text or text.startswith("<!-- Generated from "):
            continue
        for module in MODULES.findall(text):
            local = root.joinpath(*module.split("."))
            if (
                not local.with_suffix(".py").is_file()
                and not (local / "__main__.py").is_file()
            ):
                issues.append(f"{label}: missing repository Python module: {module}")
        for script in SCRIPTS.findall(text):
            if not (root / script).is_file():
                issues.append(f"{label}: missing repository Python script: {script}")
        blocks = MODEL_BLOCK.findall(text)
        if text.count(MODEL_MARKER) != len(blocks):
            issues.append(f"{label}: model marker requires one complete yaml fence")
        for block in blocks:
            try:
                model = yaml.safe_load(block)
                name = (
                    model.get("name", "doc_example")
                    if isinstance(model, dict)
                    else "doc_example"
                )
                result = ValidationResult()
                validate_model_file(Path(str(name) + ".yaml"), model, result)
                issues.extend(
                    f"{label}: complete model example: {error}"
                    for error in result.errors
                )
            except yaml.YAMLError:
                issues.append(f"{label}: complete model example is invalid YAML")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    issues = check_docs(args.root)
    for issue in issues:
        print(issue)
    print(
        f"Documentation checks: {'FAILED' if issues else 'PASSED'} ({len(issues)} issues)"
    )
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
