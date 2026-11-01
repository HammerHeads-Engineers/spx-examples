# Run an SPX example

Examples show how a person or agent can use a model and verify its behavior.
Use the [library overview](../README.md#library-overview) to choose a pack and
[the runtime workflow](../docs/RUNTIME_WORKFLOW.md) for MCP-driven work.

## First success: temperature telemetry

This tutorial registers the [temperature starter](../templates/models/temperature_sensor.yaml),
creates an isolated instance, changes its input from 20.0 to 37.5 °C, reads the
telemetry, then deletes its own instance/model. It never calls a global server
reset/prepare/run or replaces existing objects. Each run uses fresh names.
The documented command/output was verified on SPX Server `1.0.0-rc.78` with the
client dependencies in `poetry.lock`; other server/client pairs need their own check.

### Requirements

- A running SPX **test** server and a product key valid for that server.
- Capacity for one additional model and one running instance.
- A checkout of this repository, Python 3.12 and Poetry 2.2.1.
- No external protocol service, adapter or physical hardware.

Install SPX through the [product installation guide](https://docs.simplephysx.com/readme/installation-guide)
if needed. From the checkout root, run `poetry install --with dev`.
Use the server version declared by the catalog or a specifically tested compatible
version; release qualification is recorded in the published catalog's reports.

### Configure the connection

Set these variables in your local terminal. The placeholders below are not keys;
enter your real key locally and keep it out of files committed to Git.

Windows PowerShell:

```powershell
$env:SPX_BASE_URL = "http://localhost:8000"
$env:SPX_PRODUCT_KEY = "YOUR_PRODUCT_KEY"
```

Linux/macOS:

```sh
export SPX_BASE_URL="http://localhost:8000"
export SPX_PRODUCT_KEY="YOUR_PRODUCT_KEY"
```

Replace the URL with your test server's actual API address. Setting these variables
configures the client; it does not start or install a server. If your environment
already supplies them securely, use that configuration.

### Run and verify

From the checkout root on either platform:

```sh
poetry run python examples/core/temperature_quickstart.py
```

Expected output and exit code `0`:

```text
Initial temperature: 20.0 degC
After setting k__temperature_c: 37.5 degC
PASS: input changed telemetry; example instance and model removed.
```

The instance is started and checked as `RUNNING` before the input change. The
script exercises only its own instance and attempts cleanup even if verification
fails. A failed run exits nonzero; it never reports unavailable work as passed.
This verifies one control-to-telemetry behavior, not a protocol or PT100 resistance curve.

### If it fails

| Symptom | Check |
| --- | --- |
| Missing `SPX_PRODUCT_KEY` | Set it in the same terminal used to run Poetry |
| Connection/authentication error | Verify server reachability, actual API port, reported server version and key locally |
| Capacity/start error | Ensure the test license has one free model/instance slot; inspect the instance/server fault |
| Cleanup incomplete | The diagnostic names only the tutorial's objects; remove those after connectivity returns |
| No error but an existing notebook behaves differently | Notebooks have separate model/service assumptions; inspect their setup cells before running |

The tutorial avoids printing raw client/server faults that may contain sensitive
data. Use server logs locally for deeper diagnostics, and redact them before sharing.

## Choose the next example

| Location | Purpose and requirements |
| --- | --- |
| [Core temperature tutorial](core/temperature_quickstart.py) | First verified behavior and scoped cleanup |
| `core/first_simulation.py` and notebooks | Advanced/legacy client demonstrations, including ramps, noise and charts; inspect setup cells and endpoint assumptions first |
| [Smart Building examples](packs/smart_building_pack/README.md) | Weather/BMS controls on prepared pack instances |
| [Energy examples](packs/energy_pack/README.md) | OCPP and Modbus model/preset entry points |
| [Industrial examples](packs/industrial_iiot_pack/README.md) | Eurotherm setpoint notebook on prepared instances |
| [Embedded/Lab examples](packs/embedded_lab_pack/README.md) | SCPI/MQTT/LwM2M entry points; BLE example is preview-only and requires a separate adapter |

Pack profiles declare model/service selections; they do not deploy services by
themselves. A model's deployment parameters may use container DNS names such as
`mosquitto-server`; those names resolve only inside a prepared network. Use actual
reachable endpoints when running clients elsewhere. For dynamic ports, inspect
the live instance or installation output rather than assuming the defaults.

## SDK and MCP reference

The `spx-python` package ships `docs/SPX_PYTHON_LLM.md` under its installed
site-packages directory. Locate it for this Poetry interpreter with:

```sh
poetry run python -c "import sysconfig; from pathlib import Path; print(Path(sysconfig.get_path('purelib')) / 'docs' / 'SPX_PYTHON_LLM.md')"
```

Use that guide for Python client navigation, attribute writes and cleanup. The
[model reference](../docs/MODEL_LANGUAGE.md) defines YAML semantics; the
[MCP reference](../docs/MCP.md) defines live tools. Optional helper problems should
not prevent a simple supported client/API registration path.

For an independently configured MCP checkout, install dependencies and configure
the host to launch its Python executable with arguments
`-m spx_mcp stdio --repo-root <absolute-checkout-path>`. The executable is
`.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Linux/macOS.
Write tools require `--allow-write` and the intended runtime authorization.
Use host-managed MCP tools for routine work; direct CLI diagnostics can use
`poetry run python -m spx_mcp doctor --check-server`.
Product client setup remains in the product installation/MCP guide.
