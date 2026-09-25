# SPX Installer Package

The portable `.tgz` contains the installer wizard, catalog, profiles, runtime
bootstrap and generated-stack helpers. Requirements are Python 3.9+, Docker
Desktop/Engine with Compose V2, and a valid SPX Product Key for runtime use.

Run `spx-setup.command` on macOS, `spx-setup.desktop` on Linux, or
`spx-setup.bat` on Windows. The generated bundle uses Compose project `spx`,
preflights Docker, ports and existing labelled/legacy stacks, and asks before
replacement. It preserves images and volumes; a failed model or instance
bootstrap can restore the previous stack.

On Windows and macOS, if Docker Desktop is installed but its daemon is not
reachable, setup tries to start Docker Desktop and waits up to 60 seconds. If
the daemon still does not respond, an interactive setup lets you retry the
connection or quit; non-interactive setup exits with instructions. Linux keeps
its existing Docker Engine prerequisite flow.

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

New `bundle.json` files do not contain the raw Product Key. Bootstrap reads it
from `.env` or `SPX_PRODUCT_KEY` and accepts older bundles with `license_key`.
Community defaults auto-start at most five instances. Profiles remain additive
to the selected pack. During an update, old containers are held temporarily as
`spx-snapshot-*`; after a successful bootstrap they are removed by exact
container ID, without removing images or volumes. A failed Compose,
healthcheck, or bootstrap stage restores the saved container names when
possible. Legacy `spx-rollback-*` snapshots from RC65 are detected as SPX
containers and can be replaced safely.

Release artifacts are distinct: `.tgz` is the portable archive, `.run` is the
Unix self-extractor, and macOS `.pkg` is the signed/notarized native package.
See `docs/MACOS_INSTALLER_RELEASE_GATE.md` for the release checklist.
