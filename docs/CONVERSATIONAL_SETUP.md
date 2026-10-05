# Conversational SPX Setup

## User flow

Setup offers interactive keyboard controls by default, legacy text prompts, or
configuration with a local agent. `--wizard-mode interactive|legacy|agent` selects
the presentation explicitly. Existing package/profile/protocol CLI selections
continue to bypass the wizard. Without an interactive terminal, Setup explains
the fallback to legacy prompts. The agent entry is only available when the
Setup workspace/MCP implementation is present in the distribution.

Agent mode collects the product key locally or reuses the saved installation key.
It prepares a workspace before testing Docker or the SPX API. Open that directory
in a trusted local agent and say **Complete SPX setup and installation**. Further
questions, choices, approval, progress and diagnostics happen in the conversation.
The terminal monitors progress; R returns to the ordinary wizard before execution.
Closing the monitor or disconnecting MCP does not cancel or restart a running job.

The conversation starts with the user's application, devices, protocols and
integrations. If these are absent, the agent asks what SPX will be used for before
selecting a catalog. It groups unanswered setup details: local versus external
infrastructure, UI, start now, local/LAN service access, addresses/ports and update
behavior. Proposed defaults can be accepted together in the final concrete plan;
the agent must not assume that opening the workspace supplies requirements.

The full catalog is an explicit choice, not a default. Installation creates
**zero instances with no instance autostart** unless separately requested.
Model registration and service deployment are distinct: a KNX use case needs
the gateway, and MQTT needs a local broker or an explicit external provider.
The compact options response exposes installed selections and a requirements
schema; full options expose model/service dependencies. Existing gateways are
preserved unless their removal is explicitly recorded and disclosed in the plan.
Existing explicit choices, including no-start/no-UI, take precedence. Simulation
setup follows successful installation on a separate runtime request.
Use `setup_list_options(compact:false, protocols:["knx"])` or CLI
`list-options --protocol knx --json` to inspect just the needed models. Filters
are repeatable; unrelated model lists need not enter the conversation. In a
requirements-driven selected scope, protocol filters narrow the chosen packs or
profiles instead of adding every unrelated model from those packs.
Generated handoff text is English; the conversation can use the user's language.

Defaults:

| Platform | Setup workspace | Private session/credential state |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\SPX\workspace` | `%LOCALAPPDATA%\SPX\setup-state` |
| macOS | `~/Documents/SPX MCP Workspace` | `~/Library/Application Support/SPX/setup-state` |
| Linux | `~/spx-mcp-workspace` | `~/.local/share/SPX/setup-state` |

`--setup-workspace` can choose another separate directory. Setup refuses an
unmanaged nonempty directory or overlap with private state
or the installation directory. Failed dependency downloads can be retried in
the same managed directory. Starting another handoff invalidates the old draft;
an active job must instead be reconnected to.

## Client integration

The workspace contains `AGENTS.md`, `CLAUDE.md`, `INSTALLATION.md`, a private-state
reference in `setup-session.json`, and PowerShell/POSIX JSON CLI launchers. Setup
uses the existing MCP bootstrap mechanism to install a normal isolated Python
environment with YAML, HTTP, MCP and the SPX runtime client. Python >=3.10 is required for
MCP; ordinary installer modes retain the repository's Python 3.9 support.

Only project settings are created/updated; other settings and other MCP servers
are preserved. Invalid settings abort without overwriting any client profile.
Agents and global settings are never installed or modified automatically.

| Client | Generated project settings | Official reference |
| --- | --- | --- |
| Codex | `.codex/config.toml`, `mcp_servers.spx` | [Local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) |
| Claude Code | `.mcp.json`, `mcpServers.spx` | [Project MCP servers](https://code.claude.com/docs/en/mcp) |
| OpenCode v2 | `opencode.jsonc`, `mcp.servers.spx` | [MCP servers](https://opencode.ai/v2/docs/mcp-servers) |

The command uses an absolute local script path and interpreter, so starting the
client outside the workspace does not break imports. Reconnect/restart MCP after
opening the workspace. Other local clients may use the same stdio entrypoint or
the JSON CLI. The same project connection provides runtime MCP after deployment;
there is no workspace switch or routine reconnect after successful tool setup.
ChatGPT web requires a local execution bridge; attaching a folder
alone does not grant local process access. No public installer endpoint is added.

## Shared engine and tools

| MCP | CLI action | Behavior |
| --- | --- | --- |
| `setup_get_session` | `get-session` | Public selection, revision, stage, plan and diagnostics |
| `setup_list_options` | `list-options` | Full catalog, or `compact:true` for recommended selections/counts |
| `setup_update_selection` | `update-selection` | Validated patch; invalidates earlier plans |
| `setup_plan` | `plan` | Generate private staging files, inspect stack/ports, return complete plan |
| `setup_apply` | `apply` | Apply the approved plan ID/revision as an independent job |
| `setup_get_status` | `status` | Durable progress; optional compact response and bounded wait for changes |

Direct form: `python -m installer setup --state-root <private-state> <action>
--session-id <id> --json`. The generated `setup-cli.ps1` / `setup-cli.sh` supply
state location and session ID. Updates use `--selection-file <JSON>` (or `-` for
stdin); apply requires `--plan-id <id> --revision <number>`. Results use
`{"ok":true,"result":...}` or `{"ok":false,"error":...}` and nonzero CLI exit.
No CLI credential argument or MCP session-creation tool is exposed.

Sessions and plans include a public `license` summary: plan name, instance limit,
and `server_verified:false`. Local checksum-valid fields provide a planning budget;
the CO prefix gives a conservative Community cap of five. Invalid/unknown keys do
not acquire authorization from this hint. The server validates validity/expiry.
An over-budget instance selection fails before generation or Docker replacement.

Use `setup_get_status(compact:true)` once, then reuse `cursor` as `after_cursor`
with `wait_seconds:30` and `compact:true`. CLI equivalents are `status --compact
--after-cursor <cursor> --wait-seconds 30 --json` and `list-options --compact`.
Waiting happens outside session locks; MCP handles it asynchronously. The cursor
tracks lifecycle/phase changes, not every log line. A timeout returns `changed:false`
and current state. A terminal result returns immediately. Compact status omits the
catalog/selection and limits diagnostics to the last 30 lines; get-session retains
the full diagnostics for failure investigation. Report changed phases only.

Selection fields: `packages`, `profiles`, `protocols`, `install_models`,
`install_instances`, `install_spx_ui`, `model_ids`, `service_ids`, `instances`,
`start_instances`, `service_bind_addresses`, `port_mappings`, `start`,
`replace_existing`, `requirements`. Null model/service/instance lists select manifest defaults;
explicit empty lists select none. Instance definitions retain the generator's
existing shape. Bind addresses must be local; host port mapping keys are
`service:container_port/tcp|udp`. Modbus's port range must move consistently.
`start:false` generates configuration without Docker readiness or starting SPX.

### Requirements record

Agent handoff marks the session `requirements_required:true`. Existing ordinary
wizards and explicit CLI generation remain compatible without a conversation
record. A requirements-bearing plan is checked by the same engine through MCP
and CLI; it cannot bypass missing decisions merely by changing adapters.

Example selection patch for a local KNX testing environment (no instances):

```json
{
  "protocols": ["knx"],
  "service_ids": null,
  "requirements": {
    "description": "Test KNX switch actuators from my automation application",
    "catalog_scope": "selected",
    "protocols": ["knx"],
    "required_services": [],
    "external_services": {},
    "remove_services": [],
    "unresolved": [],
    "decisions": {
      "install_spx_ui": true,
      "start": true,
      "service_bind_addresses": {},
      "port_mappings": {},
      "replace_existing": false
    }
  }
}
```

`catalog_scope` is `selected`, `full_catalog` or `base`. Full catalog scope must
include every supported model on the current platform, but only protocols needed
now provision infrastructure. `base` deliberately selects no catalog models.
With full scope and `model_ids:null`, the complete catalog is resolved, including
models not assigned to a pack.
`required_services` adds infrastructure outside model dependencies. Dependencies
are resolved transitively for local services; missing required services block
explicit incomplete selections. Unsupported required protocols also block the
plan instead of silently disappearing from the configuration.

`decisions` records the exact proposed/reviewed UI, start, service-bind, port-map
and replacement values. It is not approval to execute. Changed values need an
updated record and a new plan. Unanswered questions in `unresolved`, missing
requirements or unconfirmed installed-service removals make `ready:false` before
generation or Docker inspection. Actual installation still needs one explicit
approval of the complete ready plan.

For external MQTT, declare for example:
`"external_services":{"mqtt_broker":{"endpoint":"mqtt://192.0.2.10:1883",
"provisioning":"Set mqtt_broker_host and mqtt_broker_port when creating instances"}}`.
Only separately deployed services can be external. Endpoints require an explicit
port and the matching transport; credentials, URL query parameters and fragments
are rejected. The external provider owns its dependencies. Local Compose peers
are not generated for it, and dangling external Compose dependencies are removed.
The record is persisted in the public bundle for subsequent provisioning. It does
not rewrite model YAML or automatically configure/create instances. External
providers have `verified:false` until a separate runtime communication test.

Requirement-aware bundles list every required Compose service. Transaction
readiness verifies each is running and, when available, healthy before commit;
a healthy Server API cannot conceal a missing/exited/unhealthy gateway. This
remains container/API readiness, not proof of device protocol communication.
No-start reports `required_services_checked:false`. Ordinary bundles retain
their existing readiness contract.

The agent must present the complete ready plan and receive explicit approval
in conversation before calling apply. The engine checks identity, revision,
staged files, active configuration, source payload and detected stack/ports again
before queuing and before modifying files. Changed conditions require a new plan
and new approval. It does not interpret conversational consent itself.

Preparing a draft with `replace_existing:true` is not approval to execute. An agent
may prepare that proposal without a separate preliminary confirmation, but must
explicitly include replacement in the final reviewed plan and respect refusals.
Port conflicts include an applicable `suggested_port_mappings` patch, with the
complete contiguous Modbus range where needed. Do not handwrite individual range
entries or stop unrelated services to make a proposal valid.

The active-configuration fingerprint excludes Home Assistant logs, recorder DB,
`.storage` and Matter runtime data. Their normal writes do not stale a plan.
Compose, `.env`, model/library payload, Home Assistant configuration YAML and other
installation configuration remain guarded, as do the staged payload and detected
stack/required ports. Changes to those still reject execution before modification.

The same staging engine is used by interactive and legacy generation. Those
flows keep their terminal prompts; agent execution uses no terminal `input()`.
Missing Docker, replacement decisions and conflicting ports are structured plan
errors. OS permission requests remain native user actions.

## Execution, rollback and privacy

Session locks protect selections and execution ownership. One installation job
runs at a time in the managed state. Repeated apply with the same plan returns
the same job, including after completion. POSIX workers start an independent
session; Windows uses local CIM process creation so MCP host Job Object shutdown
cannot terminate the worker. Windows keeps the caller's required runtime/Docker
environment in private state, excluding inherited SPX variables. No elevation
or service installation is introduced.

The worker journals each replaced/generated file and retains a backup. Existing
stack rollback restores bind-mounted configuration before restarting old
containers, including the previous API address. Persistent snapshot/user data
directories are excluded from promotion/rollback. An incomplete rollback or
unexpected worker death returns `RECOVERY_REQUIRED`; another operation must not
silently retry it. Backups and diagnostic state are retained for inspection.

Only `SUCCEEDED` is success. A healthy stack with failed runtime MCP refresh
reports a separate warning and instructs the user to run SPX MCP Setup/reconnect.
Setup and runtime MCP workspaces remain separate.

Credential files and staging/backup files live in owner-only private state
(Windows caller SID ACL / POSIX 0700 directories and 0600 files). The product
key is absent from the Setup workspace, client profiles, process arguments,
public plans, MCP results and sanitized progress. The committed installation's
existing `.env` retains its required local key. Stale host SPX environment cannot
override the approved session. Do not paste keys into chat or tool arguments.

## Qualification and release gate

The feature is delivered in three dependent PRs: explicit modes, transactional
sessions, then Setup MCP/workspaces. Merge them in that order; publish the agent
option only after all three parts are present. No Server/UI pins or model APIs
are changed by this feature.

Automated coverage includes selection invalidation, changing stack/configuration,
replacement rejection, conflicting/remapped TCP and UDP ports, rollback journals,
snapshot preservation, idempotency, worker failure, client setting preservation,
private state separation, Unicode launcher paths and real stdio disconnect/reconnect.
Fake format-valid keys in configuration-only tests do not qualify a licensed
stack installation.

Before release, record client versions and results separately for Windows and
macOS. Required native cases: fresh install, update, no-start, replacement refusal,
port conflict, stale plan, rollback, monitor close, client disconnect/reconnect,
saved key precedence, snapshot persistence and runtime MCP synchronization.
Perform an actual conversation-led stack installation in Codex, Claude Code and
OpenCode v2. Verify no secrets in public artifacts/logs/process command lines.
CI smoke tests and SDK transport tests do not replace those client/native cases.
The pre-existing SPX product qualification gates also remain in force.

The installer smoke workflow includes dedicated Setup contracts on Windows 2025,
Ubuntu 24.04, macOS 15 arm64 and macOS 15 Intel. Each runs the real MCP reconnect
regression and creates a fresh isolated workspace, then generates configuration
through the independent CLI worker. These jobs install dependencies normally and
retain only JUnit results, not private session state. They do not start a licensed
stack or claim native end-user installer/client qualification.
