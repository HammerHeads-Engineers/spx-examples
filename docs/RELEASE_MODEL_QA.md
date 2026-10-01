# Release model behavior checks

The BACnet, KNX, Modbus and OPC UA installer selection contains 54 models.
Starting an instance is only the first check: verify that polling continues,
numeric outputs remain finite, controls affect telemetry and scenarios recover.

## Time and counters

Time-integrating models measure elapsed simulation seconds from the instance
timer (`__timer`). Energy uses kW × seconds / 3600, or W × seconds / 3600000
for kWh. Import and export counters integrate their respective power signs.
The timer excludes time while the instance is stopped. Reset restarts counters
from model defaults. The legacy `cycle_time_s` and `_cycle_time_s` names remain
for compatibility; use the instance timer and polling interval to control time.
The internal `_elapsed_step_s` shows the integration interval actually used.

Lighting panel and KNX zone expose `lighting_power_kw`. Rated power is a
persistent input: `k__rated_zone_power_kw` (1 kW per panel zone) or
`k__rated_circuit_power_kw` (0.25 kW per KNX circuit). These are configurable
demo assumptions, not vendor specifications. Both panel energy counters use
the same load and units; switched-off lighting consumes no modeled energy.

## Scenarios and recovery

Regular scenarios are opt-in. Start one explicitly in the UI or through the
scenario API; do not start multiple overlapping overrides of the same control.
Stopping a scenario restores the values captured when it started. Scenario
conditions use their own timer, which restarts at zero on each run.

For BMS, verify normal operation, demand response and maintenance stop, then
return to automatic operation. The fan must restart without editing its alarm
readback. The zone thermal balance represents a simplified ventilated room,
with occupancy heat and an envelope tending toward 22 °C.
The demand limit caps reported power in this demonstration; it does not model
dispatching individual loads or a calibrated electrical load balance.

For Workcell, start `auto_cycle` with a present, clamped part. Check production
progress, total/OK/NOK counts and the latest serial after a completed cycle.
`tool_overtemperature` exercises the thermal interlock and recovery. Tool
temperature balances spindle heat against ambient cooling; normal production
must not fail simply because the spindle is running.

For VFD, test the speed profile, torque overload and disabling the drive.
The overload alarm compares requested torque with its limit so that limiting
the output cannot hide the overload condition. The legacy `enable` input uses
an explicit model scope to avoid colliding with the runtime lifecycle method.

## Protocols and scope

OPC UA models parameterize endpoint and namespace. Modbus slave bindings
parameterize host, port and unit identifier. The installer publishes selected
custom Modbus defaults outside 5020–5120, including Prevac 5611–5613; host-port
conflicts can be remapped through the existing service-port configurator.

Run `python tools/validate_models.py` and the behavior regressions in
`tests/core/unit/test_release_model_behavior.py`. Then use a real server to
verify actions, scenarios, polling, endpoint availability and protocol reads.
Browser tests should exercise Start/Stop/Reset, explicit scenario Start/Stop,
control inputs, charts, logs and failure states. A frozen loop must appear as
FAULT, and recreating an instance must clear samples from its previous UID.

These twins are demonstration and integration-test models. Vendor register-map
certification, physical device calibration and long-duration field fidelity
require separate tests. The generic PID accepts an external process variable;
it needs a connected plant model for a closed-loop physics demonstration.
