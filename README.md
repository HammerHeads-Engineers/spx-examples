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
