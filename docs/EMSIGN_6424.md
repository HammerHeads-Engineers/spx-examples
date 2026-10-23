# eMudhra / emSign remediation — task 6424

Status on 2026-10-23: source changes and local verification; no production
deployment or release publication. Native installers and the ARM64 image still
need release qualification. Do not close the incident based only on these edits.

## Sources and policy

- [Python advisory](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
- [Python 3.13.17 security release and installer checksums](https://www.python.org/downloads/release/python-31317/)
- [Related task 6424](https://dev.azure.com/sainaptic/Sainaptic/_workitems/edit/6424)

Minimums: pip 26.2.2, certifi 2026.10.19, uv 0.13.4 when installed.
The reviewed pip wheel URL includes its SHA-256. The old pip only downloads that
exact wheel with index access, dependency resolution and version checks disabled.
TLS verification stays enabled. Only the existing SSLKEYLOGFILE workaround is
retained; certificate and proxy configuration is inherited unchanged.

Python 3.9 remains in the application's declared compatibility range. The
installer/package bootstrap requires Python 3.10+ and stops before network access
on older interpreters. The current advisory supplies no pinned compatible pip
bootstrap for 3.9; migrate those environments instead of using an unverified fix.
CI's installation matrix now starts at 3.10. Native packages use Python 3.13.17,
whose ensurepip also contains patched pip. NumPy/SciPy have separate requirements
for 3.13 because the old locks lack Windows wheels for that interpreter.

## Changed components

`spx-examples`, based on develop / RC108:

- `installer/runtime_bootstrap.py`: version checks, hashed bootstrap, certifi
  minimum, optional installed uv upgrade, verification after installation and
  unconditional security repair even with a matching `.spx-runtime.json`.
- `spx-install.ps1`: prepare an isolated, secured installer venv before prerequisites.
  POSIX installers and generated start scripts already use the shared helper.
- `installer/mcp_workspace.py`: secure the workspace venv before editable install,
  constrain certifi during installation and verify the result.
- `pyproject.toml`, `poetry.lock`: persist certifi 2026.10.23; select compatible
  NumPy/SciPy wheels on Python 3.13 while retaining the older interpreter choices.
- `tools/secure_ci_python.py`, workflows: secure separate Poetry and dependency
  environments before use, refresh Linux system certificates, validate after sync.
- `tools/verify_python_images.py`: release qualification checks every original
  Python image selected in the generated Compose bundle before starting it.
  Selecting Home Assistant or Matter includes those providers in the same strict
  gate; the industrial starter does not deploy them. The manual **Catalog Python
  image security audit** workflow checks the complete catalog, including optional
  upstream images, independently of the industrial starter qualification.
- Windows/macOS packaging, runtime resolution and smoke workflows: Python
  3.13.17; verified SHA-256 for both official native payloads; updated Windows
  prerequisite marker so an installed 3.12 prerequisite cannot skip the new one.
- Regression and network smoke tests cover the policy and cache repair.

`spx-server`, based on develop / RC73:

- `scripts/secure_python.py`: equivalent installation security policy.
- `pyproject.toml`, `poetry.lock`: certifi minimum and lock at 2026.10.23.
- `Dockerfile`: Python 3.13.17, system CA refresh in both stages, hashed pip
  bootstrap in system and application environments before other installs, final
  environment verification.
- CI: secure tool/dependency environments, use the local semantic-release CLI,
  refresh Linux trust, rebuild Docker images with `pull: true` and `no-cache: true`.

## Existing Windows installations

Use the helper from this reviewed checkout, or the newly built installer after
it has passed qualification. Running an old installed helper will not apply the
new security policy. Back up setup configuration and snapshots before upgrading.

For each existing interpreter, run the following with its exact executable:

```powershell
$helper = "C:\path\to\fixed\spx-examples\installer\runtime_bootstrap.py"
$python = "$env:LOCALAPPDATA\SPX\workspace\.venv\Scripts\python.exe"
& $python $helper --secure-only
if ($LASTEXITCODE -ne 0) { throw "Security repair failed" }
& $python $helper --check
```

Repeat for every existing environment: `SPX\runtime\installer`,
`SPX\generated\.spx-runtime`, the MCP workspace `.venv`, developer checkout
`.venv`, and any custom `SPX_RUNTIME_HOME` / output / workspace locations.
The corresponding interpreter is `Scripts\python.exe`. Repair the bundled/base
Python separately if it will install packages; repairing a venv does not repair
its parent interpreter or the parent's ensurepip wheel.

Install the qualified native package, rerun Setup to refresh generated helpers,
then rerun MCP Setup to refresh managed workspace sources and its dependency
minimum. For a git workspace, update its source branch first. Do not overwrite
local repository changes. Recheck after dependency synchronization:

```powershell
poetry sync --with dev --no-root
poetry run python installer/runtime_bootstrap.py --check
```

Install/repair Poetry in its own secured environment before this command. A
runtime stamp is no longer a reason to skip security verification. Updating OS
trust alone does not repair old pip's vendored certificates.

## Existing macOS and Linux installations

Install vendor security updates for the OS trust store. On Debian/Ubuntu:

```sh
sudo apt-get update
sudo apt-get install --only-upgrade ca-certificates
sudo update-ca-certificates
```

With the reviewed helper, repeat for each actual interpreter:

```sh
"/path/to/venv/bin/python" /path/to/fixed/installer/runtime_bootstrap.py --secure-only
"/path/to/venv/bin/python" /path/to/fixed/installer/runtime_bootstrap.py --check
```

Include installer, generated `.spx-runtime`, MCP `.venv`, and checkout environments.
On macOS, also check `/Library/Frameworks/Python.framework/Versions/*/bin/python*`
that are actively used. The qualified native package supplies 3.13.17, but does
not retroactively update every other Python installation. Upgrade standalone uv
with its supported updater and patched OS trust; the helper upgrades pip-managed
uv inside the selected environment only.

## Container rebuild and migration

Do this in the fixed `spx-server` source checkout, for each shipped architecture:

```sh
docker build --pull --no-cache -t spx-server:emsign-reviewed .
docker run --rm --entrypoint /opt/venv/bin/python spx-server:emsign-reviewed /app/secure_python.py --check
docker run --rm --entrypoint /usr/local/bin/python spx-server:emsign-reviewed /app/secure_python.py --check
```

After image qualification and a separately authorized publication, record its
immutable digest and update the examples' compose/compatibility pins to that
published image. This change does not invent a future release tag. Existing
RC image tags remain old artefacts until replaced by a qualified build.

Back up volumes/configuration/snapshots. Set the service image to the qualified
digest, then recreate the service without removing its data volumes:

```sh
docker compose pull spx-server
docker compose up -d --force-recreate spx-server
docker compose exec spx-server /opt/venv/bin/python /app/secure_python.py --check
docker compose exec spx-server /usr/local/bin/python /app/secure_python.py --check
```

Repeat qualification for other shipped Python images (for example optional
Home Assistant/Matter images); their third-party sources are not this server
repository. Pulling the same old SPX release tag does not remediate it. Do not
remove volumes as a shortcut to recreating containers.

## Verification and remaining gates

The final local results are recorded in `EMSIGN_6424_RESULTS.md` alongside this
procedure. Re-run native installers on clean and existing Windows/macOS systems,
including MCP and matching-stamp reuse, before publication. Qualify ARM64 and any
third-party Python images separately. Keep task 6424 open until those artifact and
upgrade results have been reviewed.
