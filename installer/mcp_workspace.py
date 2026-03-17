#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create or refresh an installer-managed Codex MCP workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Mapping, Optional, Sequence


DEFAULT_SERVER_NAME = "spx"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_PRODUCT_KEY = "REPLACE_ME"
DEFAULT_WORKSPACE_NAME = "SPX Codex Workspace"
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
        help="Destination directory for the managed Codex workspace.",
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
        return home / "Documents" / DEFAULT_WORKSPACE_NAME
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
            "Installer payload is missing MCP workspace assets:\n- "
            + "\n- ".join(missing)
        )


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy_path(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            symlinks=True,
            ignore=shutil.ignore_patterns(*sorted(SKIP_ENTRY_NAMES)),
        )
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


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


def bootstrap_runtime(source_root: Path, workspace_dir: Path, python_bin: str) -> Path:
    runtime_helper = source_root / "installer" / "runtime_bootstrap.py"
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


def bootstrap_codex(workspace_dir: Path, python_bin: str, *, server_name: str, allow_write: bool) -> None:
    bootstrap_script = workspace_dir / "tools" / "codex_mcp_bootstrap.py"
    argv = [
        python_bin,
        str(bootstrap_script),
        "--repo-root",
        str(workspace_dir),
        "--server-name",
        server_name,
        "--skip-git-exclude",
    ]
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


def write_workspace_readme(workspace_dir: Path, *, server_name: str, allow_write: bool) -> None:
    mode_label = "read/write" if allow_write else "read-only"
    readme = f"""# SPX Codex Workspace

This folder was created by the packaged SPX installer so Codex can use the local
`spx-mcp` server without cloning the full repository.

## What is inside

- a managed copy of the repo assets needed by `spx-mcp`
- a local `.venv` prepared for the MCP server
- `.codex/config.toml` pointing Codex at the local MCP server id `{server_name}`

## How to use it

1. Open this folder in Codex.
2. Start a fresh thread so Codex reloads `.codex/config.toml`.
3. Use the `spx` MCP server from this workspace.

The generated config currently uses `{mode_label}` mode.
If you want to regenerate it manually, run:

```bash
sh tools/setup_codex_mcp.sh{" --read-only" if not allow_write else ""}
```

If you need a Git-backed editable repository, clone `spx-examples` separately
and bootstrap MCP there instead of editing this installer-managed copy.
"""
    (workspace_dir / WORKSPACE_README_NAME).write_text(readme, encoding="utf-8")


def write_workspace_marker(
    workspace_dir: Path,
    *,
    source_root: Path,
    workspace_python: Path,
    server_name: str,
    allow_write: bool,
) -> None:
    payload = {
        "kind": "spx-codex-mcp-workspace",
        "source_root": str(source_root),
        "workspace_python": str(workspace_python),
        "server_name": server_name,
        "allow_write": allow_write,
    }
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

    validate_source_root(source_root)
    sync_payload(source_root, workspace_dir)

    existing_env = read_dotenv(workspace_dir / ".env")
    seeded_env = read_dotenv(seed_env_path) if seed_env_path else {}
    workspace_env = build_workspace_env(existing=existing_env, seeded=seeded_env)
    write_dotenv(workspace_dir / ".env", workspace_env)

    venv_python = bootstrap_runtime(source_root, workspace_dir, args.python)
    bootstrap_codex(
        workspace_dir,
        args.python,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
    )
    write_workspace_readme(
        workspace_dir,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
    )
    write_workspace_marker(
        workspace_dir,
        source_root=source_root,
        workspace_python=venv_python,
        server_name=args.server_name,
        allow_write=bool(args.allow_write),
    )
    verify_workspace(venv_python, workspace_dir)

    print(f"[spx-mcp-workspace] Workspace directory: {workspace_dir}")
    print(f"[spx-mcp-workspace] Local venv python: {venv_python}")
    print(f"[spx-mcp-workspace] Codex config: {workspace_dir / '.codex' / 'config.toml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
