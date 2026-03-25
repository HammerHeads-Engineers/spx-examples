#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create or refresh a Codex MCP workspace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Mapping, Optional, Sequence


DEFAULT_SERVER_NAME = "spx"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_PRODUCT_KEY = "REPLACE_ME"
DEFAULT_WORKSPACE_NAME = "SPX Codex Workspace"
DEFAULT_GIT_REMOTE_URL = "https://github.com/HammerHeads-Engineers/spx-examples.git"
DEFAULT_GIT_BRANCH = "develop"
WORKSPACE_MODE_MANAGED = "managed"
WORKSPACE_MODE_GIT = "git"
WORKSPACE_README_NAME = "MCP_WORKSPACE_README.md"
WORKSPACE_MARKER_NAME = ".spx-mcp-workspace.json"
SKIP_ENTRY_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store"}
WORKSPACE_ENTRY_NAMES = (
    "installer",
    "library",
    "profiles",
    "extensions",
    "spx_mcp",
    "tools",
    "docs",
    "AGENTS.md",
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
    "INSTALLER_README.md",
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a local Codex workspace for the packaged SPX MCP tool.",
    )
    parser.add_argument(
        "--source-root",
        required=True,
        help="Installer payload root that contains spx_mcp, tools, docs, and manifests.",
    )
    parser.add_argument(
        "--workspace-dir",
        required=False,
        default=None,
        help="Destination directory for the Codex workspace.",
    )
    parser.add_argument(
        "--workspace-mode",
        choices=(WORKSPACE_MODE_MANAGED, WORKSPACE_MODE_GIT),
        default=WORKSPACE_MODE_MANAGED,
        help="Workspace bootstrap mode: managed copy or full git clone.",
    )
    parser.add_argument(
        "--python",
        required=False,
        default=sys.executable,
        help="Python 3.10+ executable used to prepare the local .venv.",
    )
    parser.add_argument(
        "--seed-env",
        required=False,
        default=None,
        help="Optional .env file used to seed SPX_PRODUCT_KEY / SPX_BASE_URL.",
    )
    parser.add_argument(
        "--server-name",
        default=DEFAULT_SERVER_NAME,
        help="Codex MCP server name written into .codex/config.toml.",
    )
    parser.add_argument(
        "--git-remote-url",
        default=DEFAULT_GIT_REMOTE_URL,
        help="Remote URL used when --workspace-mode=git.",
    )
    parser.add_argument(
        "--git-branch",
        default=DEFAULT_GIT_BRANCH,
        help="Branch name used when --workspace-mode=git.",
    )
    parser.add_argument(
        "--replace-existing-workspace",
        action="store_true",
        help="Replace an existing non-git workspace directory before cloning.",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Generate the Codex MCP config with write tools enabled.",
    )
    return parser.parse_args(argv)


def default_workspace_dir(
    home: Optional[Path] = None,
    platform_name: Optional[str] = None,
) -> Path:
    home = (home or Path.home()).expanduser().resolve()
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return home / "Documents" / DEFAULT_WORKSPACE_NAME
    if platform_name.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).expanduser().resolve() / "SPX" / "workspace"
        return home / "AppData" / "Local" / "SPX" / "workspace"
    return home / "spx-codex-workspace"


def read_dotenv(path: Path) -> dict[str, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    values: dict[str, str] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def normalize_base_url(value: str) -> str:
    return str(value or DEFAULT_BASE_URL).rstrip("/")


def build_workspace_env(
    *,
    existing: Optional[Mapping[str, str]] = None,
    seeded: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    merged = dict(existing or {})
    seeded = dict(seeded or {})

    if seeded.get("SPX_PRODUCT_KEY"):
        merged["SPX_PRODUCT_KEY"] = seeded["SPX_PRODUCT_KEY"]
    elif not merged.get("SPX_PRODUCT_KEY"):
        merged["SPX_PRODUCT_KEY"] = DEFAULT_PRODUCT_KEY

    if seeded.get("SPX_BASE_URL"):
        merged["SPX_BASE_URL"] = normalize_base_url(seeded["SPX_BASE_URL"])
    elif merged.get("SPX_BASE_URL"):
        merged["SPX_BASE_URL"] = normalize_base_url(merged["SPX_BASE_URL"])
    else:
        merged["SPX_BASE_URL"] = DEFAULT_BASE_URL

    return merged


def write_dotenv(path: Path, values: Mapping[str, str]) -> None:
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_source_root(source_root: Path) -> None:
    required_paths = [
        source_root / "spx_mcp",
        source_root / "tools" / "codex_mcp_bootstrap.py",
        source_root / "installer" / "runtime_bootstrap.py",
        source_root / "library" / "catalog" / "models.yaml",
        source_root / "pyproject.toml",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise RuntimeError(
            "Workspace source is missing required MCP assets:\n- "
            + "\n- ".join(missing)
        )


def is_git_workspace(path: Path) -> bool:
    return (path / ".git").exists()


def path_has_entries(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or path.is_file():
        return True
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy_file(src: str | Path, dest: str | Path) -> None:
    src_path = Path(src)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src_path, dest_path)
    except PermissionError:
        print(
            f"[spx-mcp-setup] Skipping unreadable payload file: {src_path}",
            file=sys.stderr,
        )


def copy_path(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            symlinks=True,
            ignore=shutil.ignore_patterns(*sorted(SKIP_ENTRY_NAMES)),
            copy_function=copy_file,
        )
        return
    copy_file(src, dest)


def sync_payload(source_root: Path, workspace_dir: Path) -> None:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    for entry_name in WORKSPACE_ENTRY_NAMES:
        if entry_name in SKIP_ENTRY_NAMES:
            continue
        entry = source_root / entry_name
        if not entry.exists():
            continue
        dest = workspace_dir / entry_name
        if dest.exists() or dest.is_symlink():
            remove_path(dest)
        copy_path(entry, dest)


def prepare_git_workspace(
    workspace_dir: Path,
    *,
    git_remote_url: str,
    git_branch: str,
    replace_existing: bool,
) -> None:
    if is_git_workspace(workspace_dir):
        return

    if path_has_entries(workspace_dir):
        if not replace_existing:
            raise RuntimeError(
                "The workspace directory already exists and is not a git checkout:\n"
                f"- {workspace_dir}\n"
                "Rerun with --replace-existing-workspace or choose a different "
                "workspace directory."
            )
        remove_path(workspace_dir)

    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "git",
            "clone",
            "--branch",
            git_branch,
            "--single-branch",
            git_remote_url,
            str(workspace_dir),
        ]
    )


def run_command(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=True,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
    )


def bootstrap_runtime(repo_root: Path, workspace_dir: Path, python_bin: str) -> Path:
    runtime_helper = repo_root / "installer" / "runtime_bootstrap.py"
    result = run_command(
        [
            python_bin,
            str(runtime_helper),
            "--venv-dir",
            str(workspace_dir / ".venv"),
        ],
        capture_output=True,
    )
    venv_python = Path(result.stdout.strip()).expanduser()
    run_command(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            str(workspace_dir),
        ]
    )
    return venv_python


def bootstrap_codex(
    workspace_dir: Path,
    python_bin: str,
    *,
    server_name: str,
    allow_write: bool,
    update_git_exclude: bool,
) -> None:
    bootstrap_script = workspace_dir / "tools" / "codex_mcp_bootstrap.py"
    argv = [
        python_bin,
        str(bootstrap_script),
        "--repo-root",
        str(workspace_dir),
        "--server-name",
        server_name,
    ]
    if not update_git_exclude:
        argv.append("--skip-git-exclude")
    if not allow_write:
        argv.append("--read-only")
    run_command(argv)


def verify_workspace(venv_python: Path, workspace_dir: Path) -> None:
    run_command(
        [
            str(venv_python),
            "-m",
            "spx_mcp",
            "doctor",
            "--repo-root",
            str(workspace_dir),
            "--json",
        ]
    )


def write_workspace_readme(
    workspace_dir: Path,
    *,
    server_name: str,
    allow_write: bool,
    workspace_mode: str,
    git_remote_url: str,
    git_branch: str,
) -> None:
    mode_label = "read/write" if allow_write else "read-only"
    if workspace_mode == WORKSPACE_MODE_GIT:
        source_summary = (
            "- a full Git clone of `spx-examples`\n"
            "- a local `.venv` prepared for the MCP server\n"
            "- `.codex/config.toml` pointing Codex at the local MCP server id "
            f"`{server_name}`\n"
            "- local git exclude updated so `.codex/config.toml` stays out of "
            "normal commits"
        )
        mode_note = (
            "This workspace keeps `.git`, branches, and remotes so you can create "
            "branches, commit model changes, and open PRs from the same folder.\n\n"
            f"The default clone target is `{git_remote_url}` on branch `{git_branch}`."
        )
    else:
        source_summary = (
            "- a managed copy of the repo assets needed by `spx-mcp`\n"
            "- a local `.venv` prepared for the MCP server\n"
            "- `.codex/config.toml` pointing Codex at the local MCP server id "
            f"`{server_name}`"
        )
        mode_note = (
            "This workspace is an installer-managed copy, not a full git checkout.\n\n"
            "If you later want to commit and push model changes, rerun `SPX MCP Setup` "
            "and choose the full git clone workflow."
        )

    readme = f"""# SPX Codex Workspace

This folder was created by the packaged SPX installer so Codex can use the local
`spx-mcp` server.

## What is inside

{source_summary}

## How to use it

1. Open this folder in Codex.
2. Start a fresh thread so Codex reloads `.codex/config.toml`.
3. Use the `{server_name}` MCP server from this workspace.

The generated config currently uses `{mode_label}` mode.
If you want to regenerate it manually, run:

```bash
sh tools/setup_codex_mcp.sh{" --read-only" if not allow_write else ""}
```

{mode_note}
"""
    (workspace_dir / WORKSPACE_README_NAME).write_text(readme, encoding="utf-8")


def write_workspace_marker(
    workspace_dir: Path,
    *,
    source_root: Path,
    repo_root: Path,
    workspace_python: Path,
    server_name: str,
    allow_write: bool,
    workspace_mode: str,
    git_remote_url: str,
    git_branch: str,
) -> None:
    payload = {
        "kind": "spx-codex-mcp-workspace",
        "source_root": str(source_root),
        "repo_root": str(repo_root),
        "workspace_python": str(workspace_python),
        "server_name": server_name,
        "allow_write": allow_write,
        "workspace_mode": workspace_mode,
    }
    if workspace_mode == WORKSPACE_MODE_GIT:
        payload["git_remote_url"] = git_remote_url
        payload["git_branch"] = git_branch
    (workspace_dir / WORKSPACE_MARKER_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    source_root = Path(args.source_root).expanduser().resolve()
    workspace_dir = (
        Path(args.workspace_dir).expanduser().resolve()
        if args.workspace_dir
        else default_workspace_dir()
    )
    seed_env_path = (
        Path(args.seed_env).expanduser().resolve()
        if args.seed_env
        else None
    )

    if args.workspace_mode == WORKSPACE_MODE_GIT:
        prepare_git_workspace(
            workspace_dir,
            git_remote_url=args.git_remote_url,
            git_branch=args.git_branch,
            replace_existing=bool(args.replace_existing_workspace),
        )
    else:
        if is_git_workspace(workspace_dir):
            raise RuntimeError(
                "The workspace directory is already a git checkout:\n"
                f"- {workspace_dir}\n"
                "Rerun with --workspace-mode=git to reuse it, or choose a "
                "different workspace directory for the managed copy flow."
            )
        validate_source_root(source_root)
        sync_payload(source_root, workspace_dir)

    repo_root = workspace_dir
    validate_source_root(repo_root)

    existing_env = read_dotenv(workspace_dir / ".env")
    seeded_env = read_dotenv(seed_env_path) if seed_env_path else {}
    workspace_env = build_workspace_env(existing=existing_env, seeded=seeded_env)
    write_dotenv(workspace_dir / ".env", workspace_env)

    venv_python = bootstrap_runtime(repo_root, workspace_dir, args.python)
    bootstrap_codex(
        workspace_dir,
        args.python,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
        update_git_exclude=args.workspace_mode == WORKSPACE_MODE_GIT,
    )
    write_workspace_readme(
        workspace_dir,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
        workspace_mode=args.workspace_mode,
        git_remote_url=args.git_remote_url,
        git_branch=args.git_branch,
    )
    write_workspace_marker(
        workspace_dir,
        source_root=source_root,
        repo_root=repo_root,
        workspace_python=venv_python,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
        workspace_mode=args.workspace_mode,
        git_remote_url=args.git_remote_url,
        git_branch=args.git_branch,
    )
    verify_workspace(venv_python, workspace_dir)

    print(f"[spx-mcp-workspace] Workspace directory: {workspace_dir}")
    print(f"[spx-mcp-workspace] Workspace mode: {args.workspace_mode}")
    print(f"[spx-mcp-workspace] Local venv python: {venv_python}")
    print(f"[spx-mcp-workspace] Codex config: {workspace_dir / '.codex' / 'config.toml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
