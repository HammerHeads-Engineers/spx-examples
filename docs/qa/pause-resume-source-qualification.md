# Pause/Resume source qualification — 2026-10-04

Decision: **NO-GO for production**. The Pause/Resume source fixes passed the
focused qualification below; published-image and native platform gates remain
open. This report is not qualification of a newly published RC.

## Tested sources and runtime

- Baseline: Examples `v1.1.0-rc.96` / Server `v1.0.0-rc.71` / UI `v1.0.0-rc.72`.
- Server: [PR #74](https://github.com/HammerHeads-Engineers/spx-server/pull/74),
  commit `7c07c36`, separate worktree from develop `02472d4`.
- UI: [PR #103](https://github.com/HammerHeads-Engineers/spx-ui/pull/103),
  app source commit `eb8810b`; polling fix included. Later commits add required
  Jest CI and capture browser evidence. Separate worktree from `216d173`.
- Examples: separate worktree from develop `9024f12`; required catalog,
  energy and scenario gates added. Existing released image pins are retained
  until Server and UI fixes have actually been published.
- Isolated Linux Docker Server: released rc.71 image with this PR's `spx_core`
  mounted read-only, plus the installed manifest, library and extensions.
  This is a source test, not an official released image.
- Base Server image digest:
  `sha256:92b09bd59da46fb69719a485d52dcbffd4062ab74fcd029a1345abfca656df08`.
- Locally built production UI image ID:
  `sha256:e76c07dbf54b68466d7def4a7e62a716f489051c34c0412b322fe15790f39337`.
- Installed 89-model manifest SHA-256:
  `6897207a94fed3c8bf10d67c9b23a95fa8348c1bad67866093c69ad3d07a3415`.
- The existing installed stack and local checkout changes were preserved.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Server lifecycle, polling, model and API v3 regressions | 91 passed | Includes 14 pause tests, one-step Run, parent refusal, shared timeout, self-worker and resume races, stale callbacks, scenario wait budgets and connection propagation |
| Server flake8 / changed-source numpydoc | Passed | Source lint also passed in GitHub Actions |
| Server CI Python 3.12 and 3.13 | 1015 passed, 25 skipped on each version | Linux CI; separate real Leshan protocol job: 11 passed |
| Live installed-model gate | 89/89 passed, no skips | Five intervals frozen clock, polling counter and physics/energy telemetry; paused Run; Resume excludes paused wall time; unchanged model communication blocks |
| Catalog physics, energy, pause scenarios | 142 passed | Includes energy steps 0.1 and 0.25 seconds and paused scenario duration/run-limit preservation |
| Jest | 41 passed | Lifecycle accessibility, backend errors, duplicate requests and history retention |
| Chromium browser E2E | 14/14 passed | Real Pause/Resume controls, two tabs, history, failed API diagnostics, System/Connections, full/partial import, snapshots, CSV and license capacity |
| Browser evidence rerun | 2/2 passed | Pause/Resume screenshot and failed-Pause scenario |
| Manual Codex browser | Passed | BMS OPC UA creation, row Start/Pause, detail Resume, frozen energy, renewed energy growth, Stop and deletion of the disposable QA instance |
| Eight real transports | 8/8 passed | OPC UA, Modbus, SCPI, MQTT, HTTP Vision, LwM2M, OCPP and KNX; protocol access remains available while physics is paused |
| Real CSMS/EVSE reconnect stress | 25/25 cycles passed | 20 at MeterValues 0.2 s plus 5 at the default 5 s; each includes Pause/Resume, frozen energy/time, Stop and repeated Release |
| Production Docker UI | Passed | Normal npm ci and complete standalone/static/public image |
| Windows UI production/standalone build | Passed | Own installed dependencies, no junctions; Node 22.21.0; /instances HTTP 200 and authenticated backend readiness |
| Broad Windows Server suite | 1001 passed, 2 failed, 32 skipped | Two socket failures reproduced on prior code: SCPI port reuse and Modbus scenario-detach cached reads. Final worker changes covered by targeted tests and Linux CI |
| Broad Windows Examples core/installer/MCP units | 532 passed, 8 failed, 22 skipped | Eight failures reproduce on baseline: the Windows bash command points to WSL without /bin/bash; download sync, macOS notarization and package shell tests cannot run correctly there |
| Linux container Examples core/installer/MCP units | 540 passed, 22 skipped | Normal LF shell scripts and required git/jq/rsync tools; platform skips are reported and do not qualify native installations |
| New release-gate unit checks | 12 passed | Missing required license fails; failures in individual models fail the entire catalog; required workflows use the no-skip runner |

Modbus register writes update the transport payload during Pause. Model actions
decode that payload after Resume; the test verifies both phases. MQTT automatic
telemetry publication is frozen with model cycles, while subscriptions and input
writes remain available. OCPP accepts protocol registration and incoming data
while paused; derived energy/power readbacks resume with model calculations.

## Evidence and remaining release gates

Local evidence is in `D:/Repos/HHE/.qa/rc96-20261004/`: `pause-catalog.xml`,
`pause-catalog-committed.log`, `pause-server-targeted-final.log`,
`pause-server-full-final.xml`, `pause-physics-final.xml`, `pause-ui-e2e-green.log`,
`pause-ui-jest-final.log`, `pause-preserved-history.png`, `pause-protocols.json`,
`pause-ui-build-final.log`, `pause-ui-standalone.json`, `pause-ocpp-cycles.json`, `pause-examples-unit.log`
`pause-examples-linux.xml` and `pause-examples-baseline.log`. No product key is copied into this report.

The disposable CI starter is qualified first and then its connections/instances
are removed before the catalog gate. This prevents occupied ports and license
slots from invalidating one-at-a-time catalog tests. Installed models are kept;
the standalone catalog test never removes a user's existing instances.

1. Merge and publish Server, then point the UI browser qualification at its
   actual published tag. Finish UI CI, merge and publish UI.
2. Pin both actual tags in all Examples installer manifests and qualification
   defaults, then publish a coherent RC. Do not predict version numbers.
3. Verify release assets, signatures, checksums and download synchronization.
4. Repeat the tests against exactly those published images. The new required
   catalog gate must run on the complete selected catalog without skips.
5. Run fresh install, upgrade, Setup/MCP Setup, restart, snapshots and rollback
   on native Windows, macOS and Linux. Test native save dialogs, print preview
   and OS integration separately.

Native Windows installer qualification for these fixes is pending. Linux
container tests and Linux CI do not qualify a native Linux installation.
No native macOS station was tested. Transport reconnect stress and earlier
snapshot/import/platform gates must be repeated on published images.
Keep production NO-GO until all these gates pass.

## PR CI handoff

Server #74 is mergeable with passing required checks. UI #103 and Examples
#129 remain drafts. Their required image-based checks intentionally still use
released Server rc.71: UI browser CI fails its new Pause/Resume test, and Examples
protocol CI reports the three new clock/energy/scenario pause regressions failing
(147 other tests pass). The source-patched stack passes these checks locally.
Publish the Server fix and update the actual image selection before rerunning;
do not skip or relax the new assertions to make the old images pass.
