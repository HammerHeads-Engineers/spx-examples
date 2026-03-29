#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create or refresh a Codex MCP workspace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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
WORKSPACE_KIND_MANAGED = "managed"
WORKSPACE_KIND_GIT = "git"
WORKSPACE_MODE_MANAGED = WORKSPACE_KIND_MANAGED
WORKSPACE_MODE_GIT = WORKSPACE_KIND_GIT
WORK_MODE_RUNTIME_MCP = "runtime_mcp"
WORK_MODE_REPO_DEV = "repo_dev"
PLACEHOLDER_PRODUCT_KEYS = {
    "REPLACE_ME",
    "CHANGE_ME",
    "YOUR_PRODUCT_KEY",
    "YOUR_KEY",
    "PRODUCT_KEY",
    "PLACEHOLDER",
}
WORKSPACE_MARKER_KIND = "spx-codex-mcp-workspace"
WORKSPACE_MARKER_VERSION = 2
WORKSPACE_README_NAME = "MCP_WORKSPACE_README.md"
WORKSPACE_MARKER_NAME = ".spx-mcp-workspace.json"
WORKSPACE_MODE_FILE_REL = Path(".codex") / "workspace_mode.toml"
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
WORKSPACE_DUPLICATE_GUARD_NAMES = set(WORKSPACE_ENTRY_NAMES) | {
    ".codex",
    ".env",
    ".github",
    ".vscode",
    "CHANGELOG.md",
    "LICENSE",
}
FINDER_DUPLICATE_RE = re.compile(
    r"^(?P<stem>.+?) (?P<copy>[2-9][0-9]*)(?P<suffix>(?:\.[^.]+)?)$"
)
WORKSPACE_MODE_FILE_RE = re.compile(r'^mode\s*=\s*"(?P<mode>[^"]+)"\s*$')
MCP_SERVER_SECTION_RE_TEMPLATE = r"(?ms)^\[mcp_servers\.{server_name}\]\s*$.*?(?=^\[|\Z)"
MCP_SERVER_ARGS_RE = re.compile(r"(?m)^args\s*=\s*(?P<value>\[[^\n]*\])\s*$")
REQUIRED_RUNTIME_WRITE_TOOLS = (
    "server_register_model_from_catalog",
    "server_register_model_and_ensure_instance",
    "server_ensure_instance",
    "server_start_instance",
    "server_stop_instance",
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
        "--workspace-kind",
        choices=(WORKSPACE_KIND_MANAGED, WORKSPACE_KIND_GIT),
        default=None,
        help="Technical workspace shape: installer-managed copy or full git clone.",
    )
    parser.add_argument(
        "--workspace-mode",
        choices=(WORKSPACE_KIND_MANAGED, WORKSPACE_KIND_GIT),
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--work-mode",
        choices=(WORK_MODE_RUNTIME_MCP, WORK_MODE_REPO_DEV),
        default=None,
        help="Semantic work mode: runtime_mcp or repo_dev.",
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
        help="Remote URL used when the resolved workspace kind is git.",
    )
    parser.add_argument(
        "--git-branch",
        default=DEFAULT_GIT_BRANCH,
        help="Branch name used when the resolved workspace kind is git.",
    )
    parser.add_argument(
        "--replace-existing-workspace",
        action="store_true",
        help="Replace an existing non-git workspace directory before cloning.",
    )
    allow_write_group = parser.add_mutually_exclusive_group()
    allow_write_group.add_argument(
        "--allow-write",
        dest="allow_write",
        action="store_true",
        default=None,
        help="Generate the Codex MCP config with write tools enabled.",
    )
    allow_write_group.add_argument(
        "--read-only",
        dest="allow_write",
        action="store_false",
        help="Generate the Codex MCP config without write tools.",
    )
    args = parser.parse_args(argv)

    if args.workspace_kind and args.workspace_mode and args.workspace_kind != args.workspace_mode:
        parser.error("--workspace-kind and --workspace-mode disagree")
    if args.workspace_kind is None and args.workspace_mode is not None:
        args.workspace_kind = args.workspace_mode
    return args


def resolve_allow_write(explicit_allow_write: Optional[bool]) -> bool:
    if explicit_allow_write is None:
        return True
    return explicit_allow_write


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

    seeded_product_key = seeded.get("SPX_PRODUCT_KEY")
    existing_product_key = merged.get("SPX_PRODUCT_KEY")
    if _is_valid_product_key(seeded_product_key):
        merged["SPX_PRODUCT_KEY"] = str(seeded_product_key).strip()
    elif _is_valid_product_key(existing_product_key):
        merged["SPX_PRODUCT_KEY"] = str(existing_product_key).strip()
    else:
        merged["SPX_PRODUCT_KEY"] = DEFAULT_PRODUCT_KEY

    if seeded.get("SPX_BASE_URL"):
        merged["SPX_BASE_URL"] = normalize_base_url(seeded["SPX_BASE_URL"])
    elif merged.get("SPX_BASE_URL"):
        merged["SPX_BASE_URL"] = normalize_base_url(merged["SPX_BASE_URL"])
    else:
        merged["SPX_BASE_URL"] = DEFAULT_BASE_URL

    return merged


def _normalize_product_key_marker(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")


def _is_valid_product_key(value: Optional[str]) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    return _normalize_product_key_marker(stripped) not in PLACEHOLDER_PRODUCT_KEYS


def read_seeded_workspace_env(
    *,
    primary_seed_env_path: Optional[Path],
    fallback_seed_env_path: Optional[Path],
) -> dict[str, str]:
    primary_values = (
        read_dotenv(primary_seed_env_path)
        if primary_seed_env_path is not None
        else {}
    )
    fallback_values = (
        read_dotenv(fallback_seed_env_path)
        if fallback_seed_env_path is not None
        else {}
    )

    merged = dict(fallback_values)
    for key, value in primary_values.items():
        if key == "SPX_PRODUCT_KEY" and not _is_valid_product_key(value):
            continue
        merged[key] = value
    if not _is_valid_product_key(merged.get("SPX_PRODUCT_KEY")) and _is_valid_product_key(
        fallback_values.get("SPX_PRODUCT_KEY")
    ):
        merged["SPX_PRODUCT_KEY"] = str(fallback_values["SPX_PRODUCT_KEY"]).strip()
    return merged


def read_process_seed_env() -> dict[str, str]:
    values: dict[str, str] = {}
    product_key = os.environ.get("SPX_PRODUCT_KEY")
    if _is_valid_product_key(product_key):
        values["SPX_PRODUCT_KEY"] = str(product_key).strip()
    base_url = os.environ.get("SPX_BASE_URL")
    if base_url:
        values["SPX_BASE_URL"] = normalize_base_url(base_url)
    return values


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


def normalize_workspace_kind(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value in {WORKSPACE_KIND_MANAGED, WORKSPACE_KIND_GIT}:
        return value
    raise RuntimeError(
        f"Unsupported workspace kind: {value}. "
        f"Expected {WORKSPACE_KIND_MANAGED} or {WORKSPACE_KIND_GIT}."
    )


def normalize_work_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value in {WORK_MODE_RUNTIME_MCP, WORK_MODE_REPO_DEV}:
        return value
    raise RuntimeError(
        f"Unsupported work mode: {value}. "
        f"Expected {WORK_MODE_RUNTIME_MCP} or {WORK_MODE_REPO_DEV}."
    )


def default_work_mode_for_kind(workspace_kind: str) -> str:
    if workspace_kind == WORKSPACE_KIND_MANAGED:
        return WORK_MODE_RUNTIME_MCP
    if workspace_kind == WORKSPACE_KIND_GIT:
        return WORK_MODE_REPO_DEV
    raise RuntimeError(f"Unsupported workspace kind: {workspace_kind}")


def workspace_kind_for_work_mode(work_mode: str) -> str:
    if work_mode == WORK_MODE_RUNTIME_MCP:
        return WORKSPACE_KIND_MANAGED
    if work_mode == WORK_MODE_REPO_DEV:
        return WORKSPACE_KIND_GIT
    raise RuntimeError(f"Unsupported work mode: {work_mode}")


def workspace_mode_file_path(workspace_dir: Path) -> Path:
    return workspace_dir / WORKSPACE_MODE_FILE_REL


def read_workspace_mode_file(workspace_dir: Path) -> Optional[str]:
    mode_path = workspace_mode_file_path(workspace_dir)
    if not mode_path.exists():
        return None

    for raw_line in mode_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = WORKSPACE_MODE_FILE_RE.match(line)
        if match:
            return normalize_work_mode(match.group("mode"))

    raise RuntimeError(
        f"Invalid workspace mode file at {mode_path}. Expected: mode = \"{WORK_MODE_RUNTIME_MCP}\""
    )


def write_workspace_mode_file(workspace_dir: Path, work_mode: str) -> None:
    mode_path = workspace_mode_file_path(workspace_dir)
    mode_path.parent.mkdir(parents=True, exist_ok=True)
    mode_path.write_text(
        "# Local SPX Codex workspace override.\n"
        "# Keep this file uncommitted and adjust only when you intentionally\n"
        "# want Codex to prefer a different work mode in this workspace.\n"
        f'mode = "{work_mode}"\n',
        encoding="utf-8",
    )


def read_workspace_marker(workspace_dir: Path) -> Optional[dict[str, object]]:
    marker_path = workspace_dir / WORKSPACE_MARKER_NAME
    if not marker_path.exists():
        return None
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid workspace metadata file: {marker_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid workspace metadata payload in {marker_path}")
    marker_kind = payload.get("kind")
    if marker_kind not in {None, WORKSPACE_MARKER_KIND}:
        raise RuntimeError(f"Unexpected workspace metadata kind in {marker_path}")
    return payload


def marker_workspace_kind(marker: Optional[Mapping[str, object]]) -> Optional[str]:
    if not marker:
        return None
    workspace_kind = marker.get("workspace_kind")
    if isinstance(workspace_kind, str):
        return normalize_workspace_kind(workspace_kind)
    legacy_workspace_mode = marker.get("workspace_mode")
    if isinstance(legacy_workspace_mode, str):
        return normalize_workspace_kind(legacy_workspace_mode)
    return None


def marker_default_work_mode(marker: Optional[Mapping[str, object]]) -> Optional[str]:
    if not marker:
        return None
    work_mode = marker.get("default_work_mode")
    if isinstance(work_mode, str):
        return normalize_work_mode(work_mode)
    workspace_kind = marker_workspace_kind(marker)
    if workspace_kind is None:
        return None
    return default_work_mode_for_kind(workspace_kind)


def normalize_duplicate_entry_name(name: str) -> Optional[str]:
    match = FINDER_DUPLICATE_RE.match(name)
    if not match:
        return None
    candidate = f"{match.group('stem')}{match.group('suffix')}"
    if candidate in WORKSPACE_DUPLICATE_GUARD_NAMES:
        return candidate
    return None


def find_duplicate_workspace_entries(workspace_dir: Path) -> list[tuple[str, str]]:
    if not workspace_dir.exists() or not workspace_dir.is_dir():
        return []
    entries = {entry.name for entry in workspace_dir.iterdir()}
    duplicates: list[tuple[str, str]] = []
    for entry_name in sorted(entries):
        normalized = normalize_duplicate_entry_name(entry_name)
        if normalized and normalized in entries:
            duplicates.append((entry_name, normalized))
    return duplicates


def assert_no_duplicate_workspace_entries(workspace_dir: Path) -> None:
    duplicates = find_duplicate_workspace_entries(workspace_dir)
    if not duplicates:
        return
    details = "\n".join(
        f"- {duplicate_name} (duplicates {canonical_name})"
        for duplicate_name, canonical_name in duplicates
    )
    raise RuntimeError(
        "The workspace directory contains suspicious duplicate entries that "
        "suggest a mixed or Finder-copied workspace:\n"
        f"{details}\n"
        "Use a clean workspace directory or remove the duplicate copies before "
        "rerunning SPX MCP Setup."
    )


def assert_workspace_marker_consistency(workspace_dir: Path) -> None:
    marker = read_workspace_marker(workspace_dir)
    if marker is None:
        return

    workspace_kind = marker_workspace_kind(marker)
    if workspace_kind is None:
        return

    has_git = is_git_workspace(workspace_dir)
    if workspace_kind == WORKSPACE_KIND_MANAGED and has_git:
        raise RuntimeError(
            "The workspace metadata says this is an installer-managed runtime_mcp "
            f"workspace, but {workspace_dir} is also a git checkout.\n"
            "This looks like a mixed legacy workspace. Use a fresh directory for "
            "runtime_mcp or remove the old git checkout first."
        )
    if workspace_kind == WORKSPACE_KIND_GIT and path_has_entries(workspace_dir) and not has_git:
        raise RuntimeError(
            "The workspace metadata says this should be a git-backed repo_dev "
            f"workspace, but {workspace_dir} is not a valid git checkout.\n"
            "This looks like a broken or mixed workspace. Replace it with a clean "
            "git clone before rerunning setup."
        )


def resolve_workspace_contract(
    *,
    workspace_dir: Path,
    explicit_workspace_kind: Optional[str],
    explicit_work_mode: Optional[str],
) -> tuple[str, str]:
    workspace_kind = normalize_workspace_kind(explicit_workspace_kind)
    work_mode = normalize_work_mode(explicit_work_mode)

    if workspace_kind and work_mode:
        if workspace_kind_for_work_mode(work_mode) != workspace_kind:
            raise RuntimeError(
                "The requested workspace kind and work mode disagree. "
                f"{work_mode} requires workspace_kind={workspace_kind_for_work_mode(work_mode)}."
            )
        return workspace_kind, work_mode

    if work_mode:
        return workspace_kind_for_work_mode(work_mode), work_mode

    if workspace_kind:
        return workspace_kind, default_work_mode_for_kind(workspace_kind)

    local_work_mode = read_workspace_mode_file(workspace_dir)
    if local_work_mode:
        return workspace_kind_for_work_mode(local_work_mode), local_work_mode

    marker = read_workspace_marker(workspace_dir)
    marker_work_mode = marker_default_work_mode(marker)
    if marker_work_mode:
        return workspace_kind_for_work_mode(marker_work_mode), marker_work_mode

    return WORKSPACE_KIND_GIT, WORK_MODE_REPO_DEV


def assert_workspace_ready_for_managed_bootstrap(workspace_dir: Path) -> None:
    assert_no_duplicate_workspace_entries(workspace_dir)
    assert_workspace_marker_consistency(workspace_dir)
    if is_git_workspace(workspace_dir):
        raise RuntimeError(
            "The workspace directory is already a git checkout:\n"
            f"- {workspace_dir}\n"
            "runtime_mcp uses an installer-managed workspace, not a repo_dev git "
            "checkout. Choose repo_dev or use a different workspace directory."
        )
    marker = read_workspace_marker(workspace_dir)
    if marker_workspace_kind(marker) == WORKSPACE_KIND_GIT:
        raise RuntimeError(
            "The existing workspace metadata marks this directory as a git-backed "
            "repo_dev workspace. Use repo_dev to reuse it, or choose a different "
            "workspace directory for runtime_mcp."
        )


def prepare_git_workspace(
    workspace_dir: Path,
    *,
    git_remote_url: str,
    git_branch: str,
    replace_existing: bool,
) -> None:
    assert_no_duplicate_workspace_entries(workspace_dir)
    assert_workspace_marker_consistency(workspace_dir)

    if is_git_workspace(workspace_dir):
        marker = read_workspace_marker(workspace_dir)
        if marker_workspace_kind(marker) == WORKSPACE_KIND_MANAGED:
            raise RuntimeError(
                "The existing workspace metadata marks this directory as an "
                "installer-managed runtime_mcp workspace, but it is also a git "
                "checkout. Use a clean repo_dev checkout instead of reusing this "
                "mixed workspace."
            )
        return

    marker = read_workspace_marker(workspace_dir)
    if marker_workspace_kind(marker) == WORKSPACE_KIND_GIT:
        raise RuntimeError(
            "The existing workspace metadata marks this directory as a git-backed "
            "repo_dev workspace, but .git is missing. Replace it with a clean "
            "checkout before rerunning setup."
        )

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
    print(
        f"[spx-mcp-workspace] Installing editable workspace into {workspace_dir / '.venv'}",
        file=sys.stderr,
    )
    run_command(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
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
    run_command(argv, cwd=workspace_dir)


def read_codex_server_args(config_path: Path, server_name: str) -> list[str]:
    config_text = config_path.read_text(encoding="utf-8")
    section_re = re.compile(
        MCP_SERVER_SECTION_RE_TEMPLATE.format(server_name=re.escape(server_name))
    )
    section_match = section_re.search(config_text)
    if section_match is None:
        raise RuntimeError(
            f"Generated Codex config is missing [mcp_servers.{server_name}] in {config_path}."
        )

    args_match = MCP_SERVER_ARGS_RE.search(section_match.group(0))
    if args_match is None:
        raise RuntimeError(
            f"Generated Codex config is missing the args field for MCP server '{server_name}' in {config_path}."
        )

    try:
        args = json.loads(args_match.group("value"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Generated Codex config has invalid args for MCP server '{server_name}' in {config_path}."
        ) from exc
    if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
        raise RuntimeError(
            f"Generated Codex config has non-string args for MCP server '{server_name}' in {config_path}."
        )
    return list(args)


def verify_workspace(
    venv_python: Path,
    workspace_dir: Path,
    *,
    server_name: str,
    allow_write: bool,
) -> None:
    config_path = workspace_dir / ".codex" / "config.toml"
    config_args = read_codex_server_args(config_path, server_name)
    config_has_allow_write = "--allow-write" in config_args
    if allow_write and not config_has_allow_write:
        raise RuntimeError(
            "Workspace bootstrap expected a write-enabled MCP config, but "
            f"{config_path} does not include --allow-write for server '{server_name}'."
        )
    if not allow_write and config_has_allow_write:
        raise RuntimeError(
            "Workspace bootstrap expected a read-only MCP config, but "
            f"{config_path} still includes --allow-write for server '{server_name}'."
        )

    doctor_argv = [
        str(venv_python),
        "-m",
        "spx_mcp",
        "doctor",
        "--repo-root",
        str(workspace_dir),
        "--json",
    ]
    if allow_write:
        doctor_argv.append("--allow-write")
    doctor_result = run_command(doctor_argv, capture_output=True)
    try:
        doctor_report = json.loads(doctor_result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Workspace bootstrap could not parse `spx_mcp doctor --json` output."
        ) from exc
    if not bool(doctor_report.get("ok")):
        problems = doctor_report.get("problems") or []
        details = "\n".join(f"- {problem}" for problem in problems) or "- unknown doctor failure"
        raise RuntimeError(
            "Workspace bootstrap failed MCP doctor verification:\n"
            f"{details}"
        )

    list_tools_argv = [
        str(venv_python),
        "-m",
        "spx_mcp",
        "list-tools",
        "--json",
    ]
    if allow_write:
        list_tools_argv.append("--allow-write")
    list_tools_result = run_command(list_tools_argv, capture_output=True)
    try:
        tool_specs = json.loads(list_tools_result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Workspace bootstrap could not parse `spx_mcp list-tools --json` output."
        ) from exc
    if not isinstance(tool_specs, list):
        raise RuntimeError(
            "Workspace bootstrap expected `spx_mcp list-tools --json` to return a list."
        )
    tool_names = {
        spec["name"]
        for spec in tool_specs
        if isinstance(spec, dict) and isinstance(spec.get("name"), str)
    }
    if allow_write:
        missing_tools = [
            tool_name
            for tool_name in REQUIRED_RUNTIME_WRITE_TOOLS
            if tool_name not in tool_names
        ]
        if missing_tools:
            raise RuntimeError(
                "Workspace bootstrap expected runtime write tools, but the generated "
                "workspace is missing:\n- "
                + "\n- ".join(missing_tools)
            )
    else:
        unexpected_tools = [
            tool_name
            for tool_name in REQUIRED_RUNTIME_WRITE_TOOLS
            if tool_name in tool_names
        ]
        if unexpected_tools:
            raise RuntimeError(
                "Workspace bootstrap generated a read-only workspace, but write tools "
                "are still exposed:\n- "
                + "\n- ".join(unexpected_tools)
            )


def write_workspace_readme(
    workspace_dir: Path,
    *,
    server_name: str,
    allow_write: bool,
    workspace_kind: str,
    work_mode: str,
    git_remote_url: str,
    git_branch: str,
) -> None:
    mode_label = "read/write" if allow_write else "read-only"
    if workspace_kind == WORKSPACE_KIND_GIT:
        source_summary = (
            "- a full Git clone of `spx-examples`\n"
            "- a local `.venv` prepared for the MCP server\n"
            "- `.codex/config.toml` pointing Codex at the local MCP server id "
            f"`{server_name}`\n"
            "- local git exclude updated so `.codex/config.toml` and "
            "`.codex/workspace_mode.toml` stay out of normal commits"
        )
        mode_note = (
            "This workspace keeps `.git`, branches, and remotes so you can build "
            "models, update tests and docs, and open PRs from the same folder.\n\n"
            f"The default clone target is `{git_remote_url}` on branch `{git_branch}`."
        )
    else:
        source_summary = (
            "- an installer-managed copy of the repo assets needed by `spx-mcp`\n"
            "- a local `.venv` prepared for the MCP server\n"
            "- `.codex/config.toml` pointing Codex at the local MCP server id "
            f"`{server_name}`\n"
            "- `.codex/workspace_mode.toml` pinned to `runtime_mcp` for MCP-first work"
        )
        mode_note = (
            "This workspace is not a full git checkout. Treat it as a runtime-first "
            "MCP workspace for live `spx-server` work.\n\n"
            "Changes here are local and may stay ephemeral unless you intentionally "
            "port them back into a repo_dev checkout later."
        )

    readme = f"""# SPX Codex Workspace

This folder was created by the packaged SPX installer so Codex can use the local
`spx-mcp` server.

## Workspace contract

- workspace kind: `{workspace_kind}`
- default work mode: `{work_mode}`

Codex and other agents should resolve work mode in this order:

1. explicit user intent
2. `.codex/workspace_mode.toml`
3. `{WORKSPACE_MARKER_NAME}`
4. `repo_dev`

## What is inside

{source_summary}

## How to use it

1. Open this folder in Codex.
2. Start a fresh thread so Codex reloads `.codex/config.toml` in the host app.
3. Use the `{server_name}` MCP server from this workspace.

The generated config currently uses `{mode_label}` mode.
Packaged workspaces default to read/write mode; use `--read-only` only when you
intentionally want inspection-only MCP access.
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
    workspace_kind: str,
    work_mode: str,
    git_remote_url: str,
    git_branch: str,
) -> None:
    payload = {
        "kind": WORKSPACE_MARKER_KIND,
        "metadata_version": WORKSPACE_MARKER_VERSION,
        "source_root": str(source_root),
        "repo_root": str(repo_root),
        "workspace_python": str(workspace_python),
        "server_name": server_name,
        "allow_write": allow_write,
        "workspace_kind": workspace_kind,
        "default_work_mode": work_mode,
    }
    if workspace_kind == WORKSPACE_KIND_GIT:
        payload["git_remote_url"] = git_remote_url
        payload["git_branch"] = git_branch
    (workspace_dir / WORKSPACE_MARKER_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_repo_root_for_workspace(repo_root: Path, workspace_kind: str) -> None:
    try:
        validate_source_root(repo_root)
    except RuntimeError as exc:
        if workspace_kind == WORKSPACE_KIND_GIT and is_git_workspace(repo_root):
            raise RuntimeError(
                "The repo_dev workspace is missing required repo assets. "
                "This usually means the checkout was partially overwritten or left "
                "in a mixed state. Replace it with a clean git clone before rerunning setup."
            ) from exc
        raise


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

    workspace_kind, work_mode = resolve_workspace_contract(
        workspace_dir=workspace_dir,
        explicit_workspace_kind=args.workspace_kind,
        explicit_work_mode=args.work_mode,
    )

    if workspace_kind == WORKSPACE_KIND_GIT:
        prepare_git_workspace(
            workspace_dir,
            git_remote_url=args.git_remote_url,
            git_branch=args.git_branch,
            replace_existing=bool(args.replace_existing_workspace),
        )
    else:
        assert_workspace_ready_for_managed_bootstrap(workspace_dir)
        validate_source_root(source_root)
        sync_payload(source_root, workspace_dir)

    repo_root = workspace_dir
    validate_repo_root_for_workspace(repo_root, workspace_kind)
    allow_write = resolve_allow_write(args.allow_write)

    existing_env = read_dotenv(workspace_dir / ".env")
    fallback_seed_env_path = None
    if workspace_kind == WORKSPACE_KIND_MANAGED:
        source_env_path = source_root / ".env"
        if source_env_path.exists():
            fallback_seed_env_path = source_env_path
    seeded_env = read_seeded_workspace_env(
        primary_seed_env_path=seed_env_path,
        fallback_seed_env_path=fallback_seed_env_path,
    )
    process_seed_env = read_process_seed_env()
    seeded_env.update(process_seed_env)
    workspace_env = build_workspace_env(existing=existing_env, seeded=seeded_env)
    write_dotenv(workspace_dir / ".env", workspace_env)

    venv_python = bootstrap_runtime(repo_root, workspace_dir, args.python)
    bootstrap_codex(
        workspace_dir,
        args.python,
        server_name=args.server_name,
        allow_write=allow_write,
        update_git_exclude=workspace_kind == WORKSPACE_KIND_GIT,
    )
    write_workspace_mode_file(workspace_dir, work_mode)
    write_workspace_readme(
        workspace_dir,
        server_name=args.server_name,
        allow_write=allow_write,
        workspace_kind=workspace_kind,
        work_mode=work_mode,
        git_remote_url=args.git_remote_url,
        git_branch=args.git_branch,
    )
    write_workspace_marker(
        workspace_dir,
        source_root=source_root,
        repo_root=repo_root,
        workspace_python=venv_python,
        server_name=args.server_name,
        allow_write=allow_write,
        workspace_kind=workspace_kind,
        work_mode=work_mode,
        git_remote_url=args.git_remote_url,
        git_branch=args.git_branch,
    )
    verify_workspace(
        venv_python,
        workspace_dir,
        server_name=args.server_name,
        allow_write=allow_write,
    )

    print(f"[spx-mcp-workspace] Workspace directory: {workspace_dir}")
    print(f"[spx-mcp-workspace] Workspace kind: {workspace_kind}")
    print(f"[spx-mcp-workspace] Default work mode: {work_mode}")
    print(f"[spx-mcp-workspace] Local venv python: {venv_python}")
    print(f"[spx-mcp-workspace] Codex config: {workspace_dir / '.codex' / 'config.toml'}")
    print(
        f"[spx-mcp-workspace] Workspace mode file: "
        f"{workspace_mode_file_path(workspace_dir)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
