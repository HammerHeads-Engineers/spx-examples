<!--
SPDX-License-Identifier: MIT
Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
See the accompanying LICENSE file for terms.
-->

# spx-examples
Runnable examples and best practices for the SPX ecosystem (SDK + Server). Covers components, models, actions, polling, PythonFile bindings, snapshots, and API v3 flows. Each example is self-contained with concise docs and tests to help you learn, prototype, and verify behavior.

## LLM-first development

This repository is prepared for LLM-first contributions so expanding or using SPX is straightforward with agent help:
- `AGENTS.md` provides the onboarding flow, conventions, and local commands.
- `docs/LLM_SPEC.md` and `docs/MODEL_LANGUAGE.md` define the contribution rules and model DSL.
- `docs/LLM_TASK_TEMPLATE.md` standardizes the LLM work plan and PR summary.
- `library/industries/<pack>/SPEC.md` captures per-pack guidance and expectations.
- `tools/validate_models.py` offers a single-command sanity check for model YAMLs.
- For tests that use the `spx_python` client, follow `SPX_PYTHON_LLM.md` (the single source of truth shipped with the spx-python package).

## Local MCP tool

This repository includes a local MCP tool for code-oriented LLM workflows against
`spx-server`. It is intended for local `stdio` use with tools such as Codex or
Claude Code and is aware of the repository catalog, profiles, packs, model
validation rules, runtime logs, `communication`, and protocol bindings.

If you install the macOS `.pkg`, the companion `SPX MCP Setup.app` can create an
installer-managed Codex workspace with `.codex/config.toml` preconfigured for
the local `spx-mcp` server. That managed workspace defaults to read-only MCP
mode; for Git-backed write workflows, continue to use a normal repository clone.

For attribute-heavy runtime workflows, prefer the batch MCP tools
`server_get_attrs` and `server_set_attrs` to reduce round trips. For time-based
numeric changes, use `server_ramp_attr`. For richer runtime behavior, prefer the
scenario tools `server_upsert_scenario`, `server_start_scenario`,
`server_stop_scenario`, and `server_delete_scenario`, which let SPX execute the
scenario DSL directly on the server side. Once a runtime scenario is proven out,
persist it into the model YAML with `repo_upsert_model_scenario`. For the server
workflow "register this catalog model and ensure one instance exists from it",
use `server_register_model_and_ensure_instance`.

- CLI entrypoint: `poetry run spx-mcp ...`
- Detailed usage: `docs/MCP.md`
- Runtime note: the official Python MCP SDK currently requires Python 3.10+,
  so use a 3.10+ Poetry environment when you want to run the MCP server itself.
  The rest of the repository continues to support Python 3.9+.
- Installation note: `spx-mcp` is available after `poetry install --with dev`.
  If you keep using `poetry install --with dev --no-root`, invoke the tool as
  `poetry run python -m spx_mcp ...`.

## Model taxonomy

Runtime model truth lives in `library/domains/` plus the catalog metadata in `library/catalog/models.yaml`.
Each catalog model entry carries a higher-level taxonomy:
- `domain_group`: `building`, `environment`, `industrial`, `energy`, or `lab`
- `device_class`: functional class such as `sensor`, `controller`, `meter`, `gateway`
- `vendor`: vendor slug or `generic`

Pack folders under `library/industries/<pack>/` are documentation-oriented views. Installer selection is driven by `library/catalog/*.yaml` and `profiles/<pack>/*.yaml`.
Each pack folder contains only `README.md`, `SPEC.md`, and a generated `MODELS.yaml` index.

## Quickstart

Follow these steps after cloning the repository to start a local SPX server, seed demo models/instances by running the tests, and (optionally) bring up the UI via the installer.

1. **Check prerequisites**
   - Docker Engine/Desktop + Docker Compose v2 (`docker compose`).
   - Python 3.9+ (CI runs 3.9-3.12).
   - (Optional) [Poetry](https://python-poetry.org/) for dependency management.

2. **Provide your SPX credentials**
   - Get your SPX product key after logging in to [simplephysx.com](https://simplephysx.com) and selecting a subscription type (Community, Trial, etc.).
   - Create a `.env` file in the project root (or export the variables in your shell) with at least your product key:
     ```bash
     cat <<'EOF' > .env
     SPX_PRODUCT_KEY=your-product-key
     # SPX_BASE_URL=http://localhost:8000
     EOF
     ```
   - Docker Compose and the test suite both read these variables, so keeping them in `.env` keeps everything in sync.

**Common environment variables**

| Variable | Purpose | Example |
| --- | --- | --- |
| `SPX_PRODUCT_KEY` | Auth key for the SPX API and integration tests. | `SPX_PRODUCT_KEY=your-product-key` |
| `SPX_BASE_URL` | Override the SPX API base URL (defaults to `http://localhost:8000`). | `SPX_BASE_URL=http://localhost:8000` |

3. **Install Python dependencies**
   - Use Poetry to install the runtime and test tooling (adds `pymodbus`, `spx-python`, pytest, etc.):
     ```bash
     poetry install --with dev --no-root
     ```

4. **Start the SPX server**
   - Bring the stack up (this repository's `docker-compose.yml` starts `spx-server` only):
     ```bash
     docker compose up --detach
     ```
   - The API is available at [http://localhost:8000](http://localhost:8000) (Swagger UI at [http://localhost:8000/docs](http://localhost:8000/docs)).
   - Wait for the health check to pass (`docker compose ps` or watch the logs) before running the tests.

5. **Seed the examples by running the tests**
   - Execute the full test suite; integration tests register models, create/update instances, run assertions, and leave the instances online:
     ```bash
     poetry run pytest
     ```
   - Some tests are skipped unless supporting services are running (e.g. MQTT broker, BACnet); use the installer workflow + packs for the full stack.

6. **Explore the playground**
   - API docs: [http://localhost:8000/docs](http://localhost:8000/docs) (OpenAPI JSON at [http://localhost:8000/docs/openapi.json](http://localhost:8000/docs/openapi.json)).
   - SPX documentation: [https://docs.simplephysx.com](https://docs.simplephysx.com).
   - SPX UI (optional): generate a bundle with the installer including UI, start it, then open [http://localhost:3000](http://localhost:3000).

When you are done, tear everything down with:
```bash
docker compose down
```

## Packs

Industry packs group models, services, and quickstart profiles around a specific domain.

- Smart-Building Pack (BMS): `library/industries/smart_building_pack/README.md`
  (quickstart: `profiles/smart_building_pack/bms_quickstart.yaml`)
- Energy Pack (e-Mobility & DER): `library/industries/energy_pack/README.md`
  (quickstart: `profiles/energy_pack/ev_csms_demo.yaml`)
- Embedded & Lab Pack: `library/industries/embedded_lab_pack/README.md`
  (quickstarts: `profiles/embedded_lab_pack/mhealth_ci.yaml`, `profiles/embedded_lab_pack/scpi_lab.yaml`)
- Industrial Pack (Industry 4.0): `library/industries/industrial_iiot_pack/README.md`
  (quickstarts: `profiles/industrial_iiot_pack/process_cell_quickstart.yaml`, `profiles/industrial_iiot_pack/iiot_monitoring.yaml`, connection matrix: `library/industries/industrial_iiot_pack/README.md`)

## Troubleshooting

- `docker compose up` fails with `Conflict. The container name "/spx-server" is already in use` — stop/remove the existing container (`docker rm -f spx-server`) or tear down the other stack (installer bundles use the same container name).
- `docker compose up` fails to bind port `502` on Linux/rootless Docker — remap the host port in `docker-compose.yml` (e.g. `1502:502`) or run Docker with privileges to bind privileged ports.
- Modbus slave + HTTP endpoint models use per-model ports defined in their YAML (e.g. `communication.modbus_slave.port`, `communication.http_endpoint.port`) — if you run with plain `docker-compose.yml`, expose those ports manually or use the installer (it auto-exposes Modbus `5020-5120` when Modbus is enabled).
- Integration tests skip or return 404s — confirm `SPX_PRODUCT_KEY` (available after logging in to [simplephysx.com](https://simplephysx.com) and selecting a subscription type) and `SPX_BASE_URL` if you are not using `http://localhost:8000`.

## Installer workflow (recommended)

This is the primary way to install and run an SPX environment:

1. Download the installer package (`.tgz` or `.zip`).
2. Extract it.
3. Run the platform-specific setup launcher (`spx-setup.*`).

The wizard will guide you through package selection, generate a local bundle, and optionally start the stack immediately.
If you press ENTER through the defaults, the wizard uses a protocol-only setup (Modbus + SCPI/ASCII), skips model installation, and keeps the SPX UI enabled.

### 1. Run the wizard

Use the platform launchers (recommended and primary):

- **macOS:** `./spx-setup.command`
- **Linux desktop:** `./spx-setup.desktop`
- **Windows:** `spx-setup.bat`
- **macOS/Linux shells:** `./spx-setup.sh`

If you extracted from a `.zip` and the launchers are not executable, run `chmod +x spx-setup.command spx-setup.sh` and retry.

The setup launchers call the underlying installer engine (`spx-install.sh`, `spx-install.ps1`, or a versioned `spx-installer-*.run` if present). You can run the engine directly if needed:

- **Bash:** `./spx-install.sh`
- **PowerShell (Windows or pwsh on macOS/Linux):** `pwsh ./spx-install.ps1`

The installer engine:

- checks that Python (`pyyaml`, `colorama`) and Docker/Compose are available,
- launches `python -m installer generate` with the wizard,
- writes the output to `build/spx-generated` (or another `--output` path you pass through).

After the wizard finishes, it will prompt to start the stack now. If you choose yes, it will run the generated start script for you.

### 2. Inspect the generated directory

Inside `build/spx-generated/` you will see:

- `docker-compose.generated.yml` – only the services selected in the wizard.
- `.env` – contains `SPX_PRODUCT_KEY=REPLACE_ME`; update it with a real key from [simplephysx.com](https://simplephysx.com) after selecting a subscription type.
- `bundle.json` – consumed by `python -m installer bootstrap`.
- `spx-start.sh` / `spx-stop.sh` and `spx-start.ps1` / `spx-stop.ps1` – start/stop helpers for Bash/zsh and PowerShell.
- `assets/` and `extensions/` – copied resources referenced by the selected services.

You can zip or commit this folder and hand it to teammates; they do not need the full repo.

### 3. Start and stop the stack (manual)

From inside the generated folder:

- **Start:**  
  - macOS/Linux: `./spx-start.sh`  
  - Windows/pwsh: `pwsh ./spx-start.ps1`
- **Stop:**  
  - macOS/Linux: `./spx-stop.sh`  
  - Windows/pwsh: `pwsh ./spx-stop.ps1`

`spx-start` performs safety checks, installs/updates the BLE adapter if needed, cleans up stale containers with `docker compose down --remove-orphans`, brings the stack up, and runs `python -m installer bootstrap --bundle bundle.json`. `spx-stop` kills the BLE adapter process and tears down the compose project. This makes the workflow approachable for junior engineers: run installer once, then use the generated start/stop scripts.

### 4. Build a distributable installer (optional)

To share the installer (wizard + manifests) without the whole repository, run:

```bash
scripts/build_installer_package.sh
```

This creates `dist/spx-installer/` and `dist/spx-installer.tgz` containing:

- `installer/`, `library/`, `profiles/`, `extensions/`
- setup launchers (`spx-setup.command`, `spx-setup.desktop`, `spx-setup.sh`, `spx-setup.bat`)
- installer engine (`spx-install.sh` / `spx-install.ps1`)
- `INSTALLER_README.md` with quickstart instructions

Hand the `.tgz` to teammates; they can extract it anywhere and run the platform launcher (`spx-setup.command`, `spx-setup.desktop`, `spx-setup.sh`, or `spx-setup.bat`) to go through the wizard locally.

### 6. Build a trusted macOS installer (Developer ID + notarization)

For a macOS-native distribution, build a signed `.pkg` that installs
`SPX Setup.app`, `SPX MCP Setup.app`, `SPX Start.app`, `SPX Stop.app`, and
`SPX Cleanup.app` into `/Applications`. `SPX Setup.app` embeds the full
installer payload inside the bundle, opens Terminal, and runs the existing
terminal-based wizard without asking the user to trust a loose downloaded
`.command` file. The other launchers operate on the generated environment in
`~/Library/Application Support/SPX/generated` or bootstrap the installer-managed
Codex MCP workspace.

1. Confirm both Developer ID certificates are present in your keychain:

```bash
security find-identity -v -p basic | grep "Developer ID"
```

2. Store notarization credentials once in the keychain:

```bash
xcrun notarytool store-credentials spx-notary \
  --apple-id "YOUR_APPLE_ID" \
  --team-id "YOUR_TEAM_ID"
```

3. Build, sign, notarize, and staple the macOS installer package:

```bash
scripts/build_macos_pkg.sh \
  --app-sign "Developer ID Application: Your Company (TEAMID1234)" \
  --sign "Developer ID Installer: Your Company (TEAMID1234)" \
  --notarytool-profile spx-notary
```

The output package is written to `dist/spx-installer-macos-<version>.pkg`. After
installation, users launch `SPX Setup.app` from `/Applications`; the installer
defaults to a user-writable output directory when it is running from a packaged
location such as `/Applications`. Once they have generated a local environment,
they can later manage it via the companion launchers in the same Applications
folder:

- `SPX MCP Setup.app` creates `~/Documents/SPX Codex Workspace`, prepares a
  local `.venv`, writes `.codex/config.toml`, and opens that folder for Codex.
  The generated MCP config defaults to read-only mode.
- `SPX Start.app` opens the generated `spx-start.command`.
- `SPX Stop.app` opens the generated `spx-stop.command`.
- `SPX Cleanup.app` stops the generated stack, asks Docker to remove the
  generated environment's containers, images, and volumes, then deletes the
  local generated/runtime directories without uninstalling the macOS apps.

### 5. Produce single-file installers (optional)

Convert the package into self-extracting files so users run a single artifact per platform:

```bash
scripts/build_self_extractors.sh --version v1.2.3
```

Outputs:

- `dist/spx-installer-v1.2.3.run` – executable for macOS/Linux that extracts to a temporary directory and launches `spx-install.sh`.
- `dist/spx-installer-v1.2.3.ps1` – PowerShell script for Windows/pwsh that unpacks to `%TEMP%` and runs `spx-install.ps1`.

Share these files directly; recipients only need Docker + Python and can execute them without manual extraction.
