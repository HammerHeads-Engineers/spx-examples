# spx-examples

Public SPX models, cataloged industry packs, runnable examples, tests, and agent guidelines.
Product installers are distributed through the protected [SPX Downloads portal](https://downloads.simplephysx.com/).

## Start here

- Read [AGENTS.md](AGENTS.md) before editing.
- For model work, read [the modeling playbook](docs/LLM_SPEC.md) and [language reference](docs/MODEL_LANGUAGE.md).
- Models live in `library/domains/`; `library/catalog/` is the discovery source of truth.
- Industry pack documentation lives in `library/industries/`, with profiles in `profiles/`.
- [MCP documentation](docs/MCP.md) covers catalog inspection and live SPX server workflows.

## Development setup

Use Python 3.12 or newer and Poetry. Python 3.10+ remains supported for MCP.

```sh
poetry install --with dev
poetry run python tools/validate_models.py
poetry run pytest tests/core/unit tests/mcp/unit tests/packs/*/unit
```

Set `SPX_BASE_URL` and `SPX_PRODUCT_KEY` locally for live server access; never commit keys.
Runtime and integration tests require the corresponding SPX stack and optional services.
The packaged SPX installer provides runtime service configurations; this repository does not ship installer payloads.

## Repository boundary

This repository starts with a fresh Git history. It contains no installer releases,
Windows/macOS packaging, signing configuration, or installer publishing workflows.
Installer releases and their history are maintained separately in the private `spx-installer` repository.

MCP runtime modules and catalog helpers live in `spx_mcp/`.
The private installer prepares Python, installs these modules, and configures the MCP clients.
This repository contains no installer code or compatibility entry points for older installers.
You can clone or update this repository independently and point your MCP client at this checkout.
