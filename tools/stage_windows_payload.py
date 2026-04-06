#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a Windows installer payload and generate a WiX file fragment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from xml.sax.saxutils import escape

DEFAULT_PAYLOAD_ENTRIES = (
    "installer",
    "library",
    "profiles",
    "extensions",
    "spx_mcp",
    "tools",
    "docs",
    "AGENTS.md",
    "LICENSE",
    "THIRD_PARTY_NOTICE.txt",
    "spx-setup.command",
    "spx-setup.desktop",
    "spx-setup.sh",
    "spx-setup.bat",
    "spx-mcp-setup.command",
    "spx-mcp-setup.sh",
    "spx-install.sh",
    "spx-install.ps1",
    "README.md",
    "pyproject.toml",
    "poetry.lock",
)

SKIP_ENTRY_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store"}
WIX_NAMESPACE = "http://wixtoolset.org/schemas/v4/wxs"
GUID_NAMESPACE = uuid.UUID("3f58fdb5-2fe9-48a2-b720-bc64f88a39de")
LAUNCHER_FILE_NAME = "SpxLauncher.exe"
MAX_WIX_ID_LENGTH = 72
WIX_ID_HASH_LENGTH = 10

SHORTCUTS = (
    (
        "shortcutSpxSetup",
        "SPX Setup",
        "Launch the SPX environment wizard.",
        "setup --pause-on-error",
    ),
    (
        "shortcutSpxMcpSetup",
        "SPX MCP Setup",
        "Create the local Codex MCP workspace for SPX.",
        "mcp-setup --pause-on-error",
    ),
    (
        "shortcutSpxStart",
        "SPX Start",
        "Start the generated SPX environment.",
        "start --pause-on-error",
    ),
    (
        "shortcutSpxStop",
        "SPX Stop",
        "Stop the generated SPX environment.",
        "stop --pause-on-error",
    ),
    (
        "shortcutSpxCleanup",
        "SPX Cleanup",
        "Remove the generated SPX environment and related Docker resources.",
        "cleanup --pause-on-error",
    ),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage a Windows installer payload and emit WiX metadata."
    )
    parser.add_argument(
        "--repo-root",
        default=str(repo_root()),
        help="Repository root that contains the installer payload sources.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the staged payload should be assembled.",
    )
    parser.add_argument(
        "--extra-path",
        action="append",
        default=[],
        help="Extra file or directory to overlay at the staged payload root.",
    )
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional JSON file that lists the staged entries and files.",
    )
    parser.add_argument(
        "--wix-fragment",
        default=None,
        help="Optional WiX fragment file for the staged payload.",
    )
    return parser.parse_args()


def copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(
        src,
        dest,
        symlinks=True,
        ignore=shutil.ignore_patterns(*sorted(SKIP_ENTRY_NAMES)),
    )


def copy_path(src: Path, dest: Path) -> None:
    if src.is_dir():
        copy_tree(src, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def overlay_path(src: Path, output_dir: Path) -> None:
    if src.is_dir():
        for child in sorted(src.iterdir(), key=lambda entry: entry.name.lower()):
            if child.name in SKIP_ENTRY_NAMES:
                continue
            target = output_dir / child.name
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            copy_path(child, target)
        return
    copy_path(src, output_dir / src.name)


def stage_payload(
    repo_root_path: Path,
    output_dir: Path,
    *,
    extra_paths: list[Path] | None = None,
) -> list[str]:
    staged_entries: list[str] = []
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for entry_name in DEFAULT_PAYLOAD_ENTRIES:
        source = repo_root_path / entry_name
        if not source.exists():
            continue
        staged_entries.append(entry_name)
        copy_path(source, output_dir / entry_name)

    for extra_path in extra_paths or []:
        overlay_path(extra_path, output_dir)

    return staged_entries


def iter_staged_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        files.append(path)
    files.sort(
        key=lambda item: (
            len(item.relative_to(root).parts),
            item.relative_to(root).as_posix().lower(),
        )
    )
    return files


def make_id(prefix: str, relative_path: Path) -> str:
    stem = relative_path.as_posix().replace("/", "_").replace(".", "_").lower()
    stem = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem).strip("_")
    if not stem:
        stem = "root"
    digest = hashlib.sha1(relative_path.as_posix().encode("utf-8")).hexdigest()[:10]
    max_stem_length = MAX_WIX_ID_LENGTH - len(prefix) - len(digest) - 1
    stem = stem[:max_stem_length].rstrip("_") or "root"
    return f"{prefix}{stem}_{digest}"


def stable_guid(kind: str, relative_path: Path) -> str:
    value = uuid.uuid5(GUID_NAMESPACE, f"{kind}:{relative_path.as_posix()}")
    return str(value).upper()


def xml_attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def launcher_component_xml(file_path: Path) -> list[str]:
    lines = [
        '      <Component Id="cmpSpxLauncherExe" Guid="2A1D0651-0B60-5DA8-80FE-1F2343090689">',
        f'        <File Id="filSpxLauncherExe" Source="{xml_attr(str(file_path))}" KeyPath="yes">',
    ]
    for shortcut_id, name, description, arguments in SHORTCUTS:
        lines.append(
            "          "
            f'<Shortcut Id="{shortcut_id}" Directory="ProgramMenuDir" Name="{xml_attr(name)}" '
            f'Description="{xml_attr(description)}" WorkingDirectory="INSTALLFOLDER" '
            f'Arguments="{xml_attr(arguments)}" />'
        )
    lines.append("        </File>")
    lines.append("      </Component>")
    return lines


def render_wix_fragment(stage_dir: Path) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<Wix xmlns="{WIX_NAMESPACE}">',
        "  <Fragment>",
        '    <ComponentGroup Id="PayloadComponents" Directory="INSTALLFOLDER">',
    ]

    for file_path in iter_staged_files(stage_dir):
        relative_path = file_path.relative_to(stage_dir)
        if relative_path.name == LAUNCHER_FILE_NAME and len(relative_path.parts) == 1:
            lines.extend(launcher_component_xml(file_path))
            continue

        component_id = make_id("cmp", relative_path)
        file_id = make_id("fil", relative_path)
        subdirectory = relative_path.parent.as_posix().replace("/", "\\")
        component_open = (
            f'      <Component Id="{component_id}" '
            f'Guid="{stable_guid("component", relative_path)}"'
        )
        if subdirectory and subdirectory != ".":
            component_open += f' Subdirectory="{xml_attr(subdirectory)}"'
        component_open += ">"

        lines.append(component_open)
        lines.append(
            f'        <File Id="{file_id}" Source="{xml_attr(str(file_path))}" KeyPath="yes" />'
        )
        lines.append("      </Component>")

    lines.extend(
        [
            "    </ComponentGroup>",
            "  </Fragment>",
            "</Wix>",
            "",
        ]
    )
    return "\n".join(lines)


def write_manifest(output_path: Path, *, staged_entries: list[str], stage_dir: Path) -> None:
    files = [path.relative_to(stage_dir).as_posix() for path in iter_staged_files(stage_dir)]
    payload = {
        "staged_entries": staged_entries,
        "files": files,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root_path = Path(args.repo_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    extra_paths = [Path(value).expanduser().resolve() for value in args.extra_path]

    staged_entries = stage_payload(repo_root_path, output_dir, extra_paths=extra_paths)

    if args.manifest_path:
        write_manifest(
            Path(args.manifest_path).expanduser().resolve(),
            staged_entries=staged_entries,
            stage_dir=output_dir,
        )

    if args.wix_fragment:
        wix_fragment_path = Path(args.wix_fragment).expanduser().resolve()
        wix_fragment_path.parent.mkdir(parents=True, exist_ok=True)
        wix_fragment_path.write_text(render_wix_fragment(output_dir), encoding="utf-8")

    print(f"Staged Windows payload at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
