# theRonda P360 KNX / theRonda S360 KNX — KNX interface notes

This note captures the KNX-facing contract needed to simulate the device 1:1 at the telegram/object level (communication objects, DPTs, and high-level semantics).

Source: Theben AG *“Presence Detector theRonda P360 KNX / theRonda S360 KNX – Hand book”* (08.2021).

## Communication objects (overview)

`Dir` legend:
- `in` — device consumes GroupValueWrite/Response (e.g. push button overrides)
- `out` — device publishes GroupValueWrite/Response (telemetry/control output)
- `in/out` — both directions

Flags (as shown in ETS/handbook) vary by object and configuration, but a practical mapping is:
- `in` → `C,W` (Communication + Write)
- `out` → `C,T` (Communication + Transmit; often also readable depending on implementation)
- `in/out` → `C,W,T` (+ `R`/`U` where supported; e.g. feedback objects)

| Nr | Object (manual name) | DPT | Dir | Notes (availability/meaning) |
|---:|---|---|---|---|
| 0 | Lighting channel C1 Switching | 1.001 | in/out | Presence & insufficient brightness → ON; time delay expired or sufficient brightness → OFF. Push button writes share the same GA. |
| 1 | Lighting channel C1 Brighter/darker | 3.007 | in/out | Present when constant light control is enabled or “dimmable in switching mode”. |
| 2 | Lighting channel C1 Send value | 5.001 | in/out | Present when constant light control is enabled or “dimmable in switching mode”. |
| 3 | Lighting channel C1 Feedback value | 5.001 | in/out | Used by constant light control (requires linking). |
| 4 | Channel C1 brightness switching/setpoint value | 9.004 | in/out | Visible when “Set brightness switching/setpoint value via bus”. Returns stored value. `0` means “Measurement OFF” in switching mode. |
| 5 | Channel C1 brightness switching/setpoint value (teach‑in) | 18.001 | in | `$81` saves current measured lux as (currently active) setpoint; `$01` calls up current setpoint (reported via object 4/6). |
| 6 | Channel C1 alternative brightness switching/setpoint value | 9.004 | in/out | Visible when “Set alternative … via bus”. `0` means “Measurement OFF” in switching mode. |
| 7 | Measurement value on lux meter | 9.004 | in | Visible when “Set brightness measurement value via bus”. Used to calculate room correction factor. |
| 8 | Room correction factor | 9.\* (2‑byte float) | out | Reported as scale factor 100 for monitoring (read/query). |
| 9 | Brightness value | 9.004 | out | Current measured lux; send cyclically and/or on change per parameters. |
| 10 | External brightness value | 9.004 | in | Used when brightness measurement source is set to external. |
| 11 | Lighting channel C2 Switching | 1.001 | in/out | Second lighting output. |
| 12 | Lighting channel C2 Brighter/darker | 3.007 | in/out | Present when constant light control is enabled or “dimmable in switching mode”. |
| 13 | Lighting channel C2 Send value | 5.001 | in/out | Present when constant light control is enabled or “dimmable in switching mode”. |
| 14 | Lighting channel C2 Feedback value | 5.001 | in/out | Used by constant light control (requires linking). |
| 22 | Lighting channel C1/C2 Select brightness switching/setpoint value | 1.003 | in | Switch between base vs alternative setpoint; ON → alternative, OFF → base. |
| 24 | Lighting channel C1/C2 Selection of constant light control / Activate‑deactivate | 1.003 | in | Starts/stops presence‑independent constant light control depending on configured channel function. |
| 25 | Lighting channel C1/C2 Standby function | 1.003 | in | Enables/disables standby (orientation light) when standby time is active. |
| 27 | Lighting channel C1/C2 Lighting time delay | 7.005 | in | Allows setting common lighting time delay (seconds) when enabled. |
| 28 | Lighting channel C1/C2 Block/unblock | 1.003 | in | Disables light outputs; evaluation continues but device stops sending via objects 0–3 / 11–14. |
| 29 | Central command | 1.001 | in | Central ON/OFF affecting channels C1/C2; OFF has special behavior if motion in last 5 seconds. |
| 30 | External scene | 18.001 | in | Receives scene numbers to block/unblock channels, start/stop control, or call internal scenes (per scene function mapping). |
| 31 | Presence channel C4.1 | 1.001 / 5.010 / 5.001 / 20.102 / 17.001 | out | Telegram sent **when presence detected** after optional switch‑on delay; DPT depends on “Telegram type C4.1”. |
| 32 | Presence channel C4.2 | 1.001 / 5.010 / 5.001 / 20.102 / 17.001 | out | Optional second telegram (**end of time delay**) when enabled. |
| 33 | Presence channel C4 Block/unblock | 1.003 | in | Disables/enables presence channel C4. |
| 34 | Presence channel C5.1 | 1.001 / 5.010 / 5.001 / 20.102 / 17.001 | out | Telegram sent **when presence detected** after optional switch‑on delay; DPT depends on “Telegram type C5.1”. |
| 35 | Presence channel C5.2 | 1.001 / 5.010 / 5.001 / 20.102 / 17.001 | out | Optional second telegram (**end of time delay**) when enabled. |
| 36 | Presence channel C5 Block/unblock | 1.003 | in | Disables/enables presence channel C5. |
| 41 | Parallel switching Trigger input/output | 1.017 | in/out | Pulse telegrams for Master/Slave or Master/Master presence sharing; cycle time parameter limits telegram load. |
| 42 | Scene input/output | 1.022 (in) / 18.001 (out) | in or out | Internal scenes: OFF → scene 1, ON → scene 2 (as “Scene input”). Or outputs a scene number on the bus when configured as “Scene output”. |
| 43 | IR external 1 switching/dimming Switching | 1.001 | out | Emitted when IR group address I is mapped to external channel 1. |
| 44 | IR external 1 switching/dimming Brighter/darker | 3.007 | out | Emitted when IR group address I is mapped to external channel 1. |
| 45 | IR external 2 switching/dimming Switching | 1.001 | out | Emitted when IR group address II is mapped to external channel 2. |
| 46 | IR external 2 switching/dimming Brighter/darker | 3.007 | out | Emitted when IR group address II is mapped to external channel 2. |
| 47 | IR external blinds 1 Blinds up/down | 1.008 | out | Emitted when IR group address I is mapped to external blinds 1. |
| 48 | IR external blinds 1 Open/close slats | 1.009 | out | Emitted when IR group address I is mapped to external blinds 1. |
| 49 | IR external blinds 2 Blinds up/down | 1.008 | out | Emitted when IR group address II is mapped to external blinds 2. |
| 50 | IR external blinds 2 Open/close slats | 1.009 | out | Emitted when IR group address II is mapped to external blinds 2. |
| 51 | Presence test mode | 1.001 | in | ON starts test mode for configured duration; OFF ends early (device restarts). |
| 52 | Brightness test mode | 1.001 | in | ON starts test mode for configured duration; OFF ends early (device restarts). |
| 53 | Software version | 217.001 | out | Queried via read; response is 2‑byte payload per DPT 217.001 mapping in the handbook. |

## SPX model mapping (this repo)

The initial simulator model is `library/domains/iot/theben/theronda_p360__knx.yaml`.

Defaults (group addresses):
- Lighting C1: `3/0/1` (obj0), `3/0/5` (obj4), `3/0/7` (obj6), `3/0/9` (obj8), `3/0/10` (obj9), `3/0/11` (obj10)
- Lighting C2: `3/1/1` (obj11)
- Shared: `3/2/1` (obj22), `3/2/3` (obj25), `3/2/4` (obj27), `3/2/5` (obj28), `3/2/6` (obj29)
- Presence: `3/3/1` (obj31), `3/3/2` (obj32), `3/3/3` (obj33), `3/3/4` (obj34), `3/3/5` (obj35), `3/3/6` (obj36)
- Parallel trigger: `3/4/1` (obj41)

Notes:
- Presence outputs (obj31/32/34/35) are currently implemented as `switch command` semantics (1-bit ON/OFF). Other telegram types (value/percent/HVAC/scene) are documented above but not wired as separate bindings in v1.
- Constant light control objects, scene objects, IR external objects and test-mode objects are documented above but not bound in v1.
