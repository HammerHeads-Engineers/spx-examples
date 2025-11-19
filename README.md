<!--
SPDX-License-Identifier: MIT
Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
See the accompanying LICENSE file for terms.
-->

# spx-examples
Runnable examples and best practices for the SPX ecosystem (SDK + Server). Covers components, models, actions, polling, PythonFile bindings, snapshots, and API v3 flows. Each example is self-contained with concise docs and tests to help you learn, prototype, and verify behavior.

## Quickstart

Follow these steps after cloning the repository to spin up the SPX stack, materialise the sample models, and explore them in the UI.

1. **Check prerequisites**
   - Docker and Docker Compose available in your shell (Compose v2+ recommended).
   - Python 3.11 or newer for running the tests and local tooling.
   - (Optional) [Poetry](https://python-poetry.org/) for dependency management.

2. **Provide your SPX credentials**
   - Create a `.env` file in the project root (or export the variables in your shell) with at least your product key:
     ```bash
     cat <<'EOF' > .env
     SPX_PRODUCT_KEY=your-product-key
     # SPX_LICENSE_KEY=optional-license-if-required
     EOF
     ```
   - Docker Compose and the test suite both read these variables, so keeping them in `.env` keeps everything in sync.

3. **Install Python dependencies**
   - Use Poetry to install the runtime and test tooling (adds `pymodbus`, `spx-python`, pytest, etc.):
     ```bash
     poetry install --with dev
     ```

4. **Start the SPX services**
   - Bring the stack up; this launches both the API server and the UI:
     ```bash
     docker compose up --detach
     ```
   - Wait for the health check to pass (`docker compose ps` or watch the logs) before running the tests.

5. **Seed the examples by running the tests**
   - Execute the full test suite; each integration test bootstraps its model, creates an instance, runs assertions, and leaves the instance online when it exits:
     ```bash
     poetry run pytest
     ```
   - If the product or license key is missing/invalid the SPX API returns 404s, so double-check `.env` if you see those errors.

6. **Explore the playground**
   - With the tests complete, the freshly created instances stay active. Open [http://localhost:3000](http://localhost:3000) (served by the `spx-ui` container) to inspect and interact with them.

When you are done, tear everything down with:
```bash
docker compose down
```

## Installer workflow

Prefer running an interactive wizard and sharing a self-contained bundle? Use the installer scripts.

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
- `.env` – contains `SPX_PRODUCT_KEY=REPLACE_ME`; update it with a real key.
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
