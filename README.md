<!--
SPDX-License-Identifier: MIT
Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
See the accompanying LICENSE file for terms.
-->

# spx-examples
Runnable examples and best practices for the SPX ecosystem (SDK + Server). Covers components, models, actions, polling, PythonFile bindings, snapshots, and API v3 flows. Each example is self-contained with concise docs and tests to help you learn, prototype, and verify behavior.

## Quickstart

Follow these steps after cloning the repository to start a local SPX server, seed demo models/instances by running the tests, and (optionally) bring up the UI via the installer.

1. **Check prerequisites**
   - Docker Engine/Desktop + Docker Compose v2 (`docker compose`).
   - Python 3.9+ (CI runs 3.9–3.12).
   - (Optional) [Poetry](https://python-poetry.org/) for dependency management.

2. **Provide your SPX credentials**
   - Get your SPX product key after logging in to [simplephysx.com](https://simplephysx.com) and selecting a subscription type (Community, Trial, etc.).
   - Create a `.env` file in the project root (or export the variables in your shell) with at least your product key:
     ```bash
     cat <<'EOF' > .env
     SPX_PRODUCT_KEY=your-product-key
     # SPX_API_URL=http://localhost:8000
     EOF
     ```
   - Docker Compose and the test suite both read these variables, so keeping them in `.env` keeps everything in sync.

3. **Install Python dependencies**
   - Use Poetry to install the runtime and test tooling (adds `pymodbus`, `spx-python`, pytest, etc.):
     ```bash
     poetry install --with dev
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
  (quickstarts: `profiles/industrial_iiot_pack/opcua_line_quickstart.yaml`, `profiles/industrial_iiot_pack/iiot_monitoring.yaml`)

## Troubleshooting

- `docker compose up` fails with `Conflict. The container name "/spx-server" is already in use` — stop/remove the existing container (`docker rm -f spx-server`) or tear down the other stack (installer bundles use the same container name).
- `docker compose up` fails to bind port `502` on Linux/rootless Docker — remap the host port in `docker-compose.yml` (e.g. `1502:502`) or run Docker with privileges to bind privileged ports.
- Integration tests skip or return 404s — confirm `SPX_PRODUCT_KEY` (available after logging in to [simplephysx.com](https://simplephysx.com) and selecting a subscription type) and `SPX_API_URL` if you are not using `http://localhost:8000`.

## Installer workflow

Prefer running an interactive wizard and sharing a self-contained bundle (optionally including the UI + supporting protocol services)? Use the installer scripts.

### 1. Run the wizard

- **macOS/Linux shells:** `./spx-install.sh`
- **PowerShell (Windows or pwsh on macOS/Linux):** `pwsh ./spx-install.ps1`

Both wrappers:

- check that Python (`pyyaml`, `colorama`) and Docker/Compose are available,
- launch `python -m installer generate` with the wizard,
- write the output to `build/spx-generated` (or another `--output` path you pass through).

### 2. Inspect the generated directory

Inside `build/spx-generated/` you will see:

- `docker-compose.generated.yml` – only the services selected in the wizard.
- `.env` – contains `SPX_PRODUCT_KEY=REPLACE_ME`; update it with a real key from [simplephysx.com](https://simplephysx.com) after selecting a subscription type.
- `bundle.json` – consumed by `python -m installer bootstrap`.
- `spx-start.sh` / `spx-stop.sh` and `spx-start.ps1` / `spx-stop.ps1` – start/stop helpers for Bash/zsh and PowerShell.
- `assets/` and `extensions/` – copied resources referenced by the selected services.

You can zip or commit this folder and hand it to teammates; they do not need the full repo.

### 3. Start and stop the stack

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
- `spx-install.sh` / `spx-install.ps1`
- `INSTALLER_README.md` with quickstart instructions

Hand the `.tgz` to teammates; they can extract it anywhere and run `./spx-install.sh` (or `pwsh ./spx-install.ps1`) to go through the wizard locally.

### 5. Produce single-file installers (optional)

Convert the package into self-extracting files so users run a single artifact per platform:

```bash
scripts/build_self_extractors.sh --version v1.2.3
```

Outputs:

- `dist/spx-installer-v1.2.3.run` – executable for macOS/Linux that extracts to a temporary directory and launches `spx-install.sh`.
- `dist/spx-installer-v1.2.3.ps1` – PowerShell script for Windows/pwsh that unpacks to `%TEMP%` and runs `spx-install.ps1`.

Share these files directly; recipients only need Docker + Python and can execute them without manual extraction.
