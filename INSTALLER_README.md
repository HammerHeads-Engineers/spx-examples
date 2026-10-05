# SPX Installer Package

The portable `.tgz` contains the installer wizard, catalog, profiles, runtime
bootstrap and generated-stack helpers. Requirements are Python 3.9+, Docker
Desktop/Engine with Compose V2, and a valid SPX Product Key for runtime use.

Run `spx-setup.command` on macOS, `spx-setup.desktop` on Linux, or
`spx-setup.bat` on Windows. Docker is checked only when Setup will start a local
stack (interactive Setup or explicit `--start`). Artifact-only generation,
`--no-start`, help, and bootstrap commands do not require a local Docker daemon.
The generated bundle uses Compose project `spx`, preflights Docker, ports and
existing labelled/legacy stacks, and asks before replacement. It preserves
images and volumes; a failed model or instance bootstrap can restore the
previous stack.

All Setup modes (interactive, legacy text prompts, and agent conversation) also
prepare MCP and CLI tools automatically. The final result reports stack and tool
readiness separately. Open the reported workspace in your local agent; its
project-local `spx` MCP contains both installation and runtime tools. With agent
Setup, continue using the same workspace and conversation after installation.
No second MCP Setup or reconnect is needed. Initial project trust/tool permissions
still belong to your agent client. Keys remain in private per-user Setup state.

Use `spx.ps1` on Windows or `spx.sh` on macOS/Linux in that workspace:
`doctor --check-server --json`, `list-tools --json`, or
`call server_list_instances --json`. Supply runtime tool arguments through
`--arguments-file <JSON file>`, never a product-key process argument. With
`--no-start`, tools are still installed and live commands report `SPX_NOT_STARTED`
until SPX Start completes. MCP requires Python 3.10+; packaged desktop installers
prepare the supported interpreter. SPX MCP Setup remains available for repair
and repository-development workspaces rather than as a required follow-up step.

Before changing a stack, Setup checks whether required host ports are already
used. If an unrelated application or container holds a port, Setup shows the
port and owner when available, asks you to stop or reconfigure it yourself,
then press Enter to check again or `Q` to quit. Setup does not stop unrelated
applications or containers. Once the required ports are free, it continues;
without an interactive terminal it prints the same guidance and exits. This
port-retry flow is shared by Windows, macOS, and Linux.

On macOS and Windows, Setup attempts to start Docker Desktop automatically.
If Docker CLI, Docker Desktop, its daemon, or Compose is unavailable, it prints
the matching installation/recovery steps in English. In an interactive
terminal, start or fix Docker as instructed, then press Enter to retry the
checks for up to 60 seconds, or type `Q` to quit. Enter retries the connection
without starting Docker Desktop again; Setup re-detects the CLI and verifies
Docker Engine and Compose before continuing. If the terminal is unavailable,
Setup exits with the same instructions and can be rerun after Docker is ready.
On Linux, Setup never starts Docker Engine or runs `sudo` for you; it explains
how to install/start Engine and Compose, then lets you retry with Enter or quit
with `Q`.

For each selected service that publishes protocol ports, the wizard asks
whether to keep it local on `127.0.0.1` (default) or bind it to a selected
private IPv4 address for LAN access. Non-interactive generation stays
local-only. The start scripts verify that a saved LAN address still belongs to
the host and stop before changing the stack if it has changed. BACnet/IP and
KNXnet/IP discovery is most reliable on the same subnet; firewall and routing
configuration are not changed by the installer. Advanced users can edit the
`SPX_BIND_<SERVICE_ID>` values in `.env`; `BACNET_BIND_ADDR` remains a legacy
BACnet override.

The native macOS `.pkg` starts `SPX Setup.app` automatically after a normal
GUI installation. Command-line, CI and managed installations skip that GUI
launch. The Windows `.exe` offers a `Launch SPX Setup` button on its success
screen. The portable `.run`, `.ps1` and `.tgz` launchers keep their existing
wizard behavior.

When the wizard starts the generated stack successfully with the UI enabled,
the default browser opens at `http://localhost:3000`. Set
`SPX_OPEN_BROWSER=0` to disable automatic browser opening. Set
`SPX_SKIP_AUTO_SETUP=1` when an automation wrapper must suppress the macOS
post-install wizard launch.

The installer keeps its private Python interpreter separate from the generated
stack runtime. Paths containing spaces, including macOS `Library/Application
Support`, are passed as single arguments. If a system interpreter must be
selected explicitly, use `SPX_SYSTEM_PYTHON_BIN`; `PYTHON_BIN` is reserved for
backward compatibility with the installer launcher and is not forwarded to a
generated start script.

Generated Windows start and stop commands run through the bundled Python
stack helper. The `.bat` files and native launcher call Python directly; the
PowerShell files are short wrappers for users who prefer them. This keeps the
transaction, health checks and rollback in the shared stack helper instead of
embedding a per-install PowerShell program.

New `bundle.json` files do not contain the raw Product Key. Bootstrap reads it
from `.env` or `SPX_PRODUCT_KEY` and accepts older bundles with `license_key`.
The wizard checks the key format and asks again for malformed input without
echoing it: 30 uppercase Base32 characters (`A-Z`, `2-7`), either continuous or
in six groups of five separated by dashes. Pasted surrounding whitespace is
trimmed in the wizard. Generated start commands check the effective key before
runtime preparation or replacement of an existing stack. The wizard's selected
key takes precedence over an inherited `SPX_PRODUCT_KEY` when it launches the
stack; standalone start commands retain Compose's environment-over-`.env`
precedence. Format validation does not confirm license validity or expiry;
the server still checks those.

Community defaults auto-start at most five instances. Profiles remain additive
to the selected pack. During an update, old containers are held temporarily as
`spx-snapshot-*`; after a successful bootstrap they are removed by exact
container ID, without removing images or volumes. A failed Compose,
healthcheck, or bootstrap stage restores the saved container names when
possible. Legacy `spx-rollback-*` snapshots from RC65 are detected as SPX
containers and can be replaced safely.

On a startup failure, Setup saves the readiness result, Docker state and recent
server/UI logs to `logs/start-<transaction>.json` in the generated directory
before cleaning up failed containers. Secret values from `.env` are redacted.
Terminal messages identify Docker, container health and host API errors.
Loopback API checks bypass proxies and use IPv4 by default.
Plain HTTP loopback checks use a direct HTTP connection without initializing TLS,
so an inaccessible inherited `SSLKEYLOGFILE` cannot block readiness or rollback.
Configured HTTPS endpoints keep their normal TLS handling.

Rollback success is verified against the restored containers and host API.
An incomplete restore is reported as an error and retains the recovery snapshot
and transaction Compose file. After a verified rollback, run **SPX Setup** from
the SPX application or Windows Start menu to retry. Include the saved diagnostic
file when reporting a startup failure.

Release artifacts are distinct: `.tgz` is the portable archive, `.run` is the
Unix self-extractor, and macOS `.pkg` is the signed/notarized native package.
See `docs/MACOS_INSTALLER_RELEASE_GATE.md` for the release checklist.
