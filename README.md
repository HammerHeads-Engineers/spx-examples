<!--
SPDX-License-Identifier: MIT
Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
See the accompanying LICENSE file for terms.
-->

# spx-examples
Runnable examples and best practices for the SPX ecosystem (SDK + Server). Covers components, models, actions, polling, PythonFile bindings, snapshots, and API v3 flows. Each example is self-contained with concise docs and tests to help you learn, prototype, and verify behavior.

## Quickstart

Follow these steps right after cloning the repository to get an SPX playground up and running locally:

1. **Install dependencies**
   - Make sure you have Docker, Docker Compose, and Python 3.11+ available on your machine.
   - (Optional but recommended) Install the Python tooling with Poetry:
     ```bash
     poetry install
     ```

2. **Create the environment file**
   - Copy the sample `.env` file if you have one or create a new one in the project root.
   - Add your SPX license token, for example:
     ```bash
     echo "SPX_LICENSE_KEY=your-license-token" > .env
     ```

3. **Start the SPX services**
   - Launch the server stack in the background:
     ```bash
     docker compose up --detach
     ```

4. **Generate the sample data via tests**
   - Run the unit test suite to hydrate the environment with example devices and flows:
     ```bash
     poetry run pytest
     ```

5. **Explore in the UI (optional)**
   - If you already have `spx-ui` running locally, open your browser at [http://localhost:3000](http://localhost:3000) to start experimenting with the freshly created examples.

When you are done, you can stop the Docker services with:
```bash
docker compose down
```
