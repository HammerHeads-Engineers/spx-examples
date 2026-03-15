# Local MCP Tool

`spx-examples` includes a local MCP tool intended for code-oriented LLM workflows.
It is a repo tool, not an example project: the MCP server understands the local
catalog, profiles, packs, model validation rules, and a running SPX server.

## Scope

The current MCP server is designed for local `stdio` workflows:

- inspect repository packs, profiles, and models
- validate catalog models with the repository validator
- inspect models and instances on a running SPX server
- inspect runtime logs, communication trees, and protocol bindings
- optionally perform write operations such as model registration, instance lifecycle
  control, and attribute writes

## Runtime requirements

- Python 3.10+ for the official `mcp` SDK
- project dependencies installed with dev extras
- `SPX_PRODUCT_KEY` for live server access
- `SPX_BASE_URL` if the server is not running at `http://localhost:8000`

Example setup on Windows:

```powershell
poetry env use C:\Python314\python.exe
poetry install --with dev
```

## Bootstrap Codex config

To generate a local Codex MCP config for this repository without committing
machine-specific paths, use one of the bootstrap scripts below. They create
`<repo>/.codex/config.toml` and add `.codex/config.toml` to the local
git exclude file for the worktree.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_codex_mcp.ps1
```

Linux or macOS:

```bash
sh tools/setup_codex_mcp.sh
```

Optional flags:

- `--read-only` to omit `--allow-write`
- `--server-name custom_name` to use a different Codex MCP id

The generated config prefers the local `.venv` Python interpreter when present
and otherwise falls back to `poetry run python -m spx_mcp ...`.

If you intentionally keep the repo in `--no-root` mode, use the module form:

```powershell
poetry run python -m spx_mcp list-tools
```

## Commands

List the available tools:

```powershell
poetry run spx-mcp list-tools
poetry run spx-mcp list-tools --allow-write
poetry run python -m spx_mcp list-tools
```

Check local prerequisites:

```powershell
poetry run spx-mcp doctor
poetry run spx-mcp doctor --json
poetry run python -m spx_mcp doctor
```

Run the MCP server over `stdio`:

```powershell
poetry run spx-mcp stdio
poetry run spx-mcp stdio --allow-write
poetry run python -m spx_mcp stdio
```

Run the live end-to-end smoke test against a local `spx-server`:

```powershell
C:\Python314\python.exe tools\mcp_live_smoke.py
```

This script launches `spx_mcp` over `stdio`, connects with an MCP client,
validates a catalog model, registers it on the running server, creates an
instance, inspects diagnostics, and exercises basic lifecycle operations.

## Tool groups

Read-only and diagnostics are always exposed:

- `repo_list_packs`
- `repo_list_profiles`
- `repo_find_models`
- `repo_get_model`
- `repo_validate_model`
- `health`
- `server_list_models`
- `server_list_instances`
- `server_get_instance`
- `server_get_attr`
- `server_get_node`
- `server_get_logs`
- `server_get_communication`
- `server_get_bindings`
- `server_diagnose_instance`

Write tools are exposed only with `--allow-write`:

- `server_register_model_from_catalog`
- `server_ensure_instance`
- `server_start_instance`
- `server_stop_instance`
- `server_reset_instance`
- `server_set_attr`
- `repo_bootstrap_pack`
- `repo_bootstrap_profile`

## Notes

- The MCP tool reuses `spx_python` as the primary operational layer.
- Repository-specific glue is limited to catalog lookup, model validation, and
  convenience bootstrap flows.
- For runtime diagnostics, the tool can inspect generic tree paths, instance logs,
  communication blocks, and bindings.
