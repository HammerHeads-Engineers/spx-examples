# Energy Pack Examples

Start with the [temperature tutorial](../../README.md#first-success-temperature-telemetry),
then use the [Energy pack guide](../../../library/industries/energy_pack/README.md)
to choose a meter or the [OCPP EV/CSMS preset](../../../profiles/energy_pack/ev_csms_demo.yaml).

There is currently no pack-specific executable tutorial here. The preset selects
models/services and requires a prepared test deployment; it does not start them
by itself. For an OCPP session, run both peers with reachable WebSocket endpoints
and verify their exchange rather than treating instance startup as protocol proof.
