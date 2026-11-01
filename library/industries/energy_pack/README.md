# Energy Pack (e-Mobility & DER)

Foundation for energy-native DER / e-mobility scenarios. Includes OCPP 1.6 charge
point + CSMS twins, Modbus EVSEs, and power-meter telemetry for charging and
power-flow demos.

## Start here

| Item | What to use |
| --- | --- |
| First SPX result | [Temperature tutorial](../../../examples/README.md#first-success-temperature-telemetry) |
| One-instance protocol model | `Energy.EnergyMeterDirisA10.Modbus`; inspect its live attributes and assigned Modbus endpoint |
| Multi-instance OCPP demo | [EV/CSMS profile](../../../profiles/energy_pack/ev_csms_demo.yaml) |
| Live workflow | [MCP/runtime guide](../../../docs/RUNTIME_WORKFLOW.md) |

Use a compatible SPX test server with capacity for the selected models/instances.
An agent can discover/register the meter, start a uniquely named instance and
inspect its current measurements. A protocol claim additionally needs an actual
Modbus read against its reachable endpoint. The OCPP profile needs both twins
and correct WebSocket wiring; creating an EVSE alone does not demonstrate a session.
Stop/delete only the demo objects when finished.

Profiles select models/services rather than deploying them. Container DNS names
and ports below are defaults in a prepared deployment. Use actual host bindings
from the live instance or installation output for external clients.

The CSMS also handles Authorize, StartTransaction and StopTransaction, with
`k__authorization_status` controlling the returned tag status. Each start gets
a distinct transaction ID within the protocol instance; IDs restart on instance
recreation. Boot and heartbeat responses use the current UTC time. This is a
single-charge-point simulator without billing or an authorization database.
These response fields were introduced in SPX Server `v1.0.0-rc.73`. Current
catalog compatibility and qualification are declared separately in release assets.

The legacy three-phase Modbus meter retains container port 502 by default.
Override `modbus_host` and `modbus_port` when using a dedicated instance port;
the client must use the corresponding published host port from `bundle.json`.

The MQTT energy meter uses the bundled `mosquitto-server:1883` by default;
`mqtt_broker_host`, `mqtt_broker_port`, and `mqtt_topic_prefix` remain overridable.
Energy is integrated from elapsed simulation seconds, independently of polling
frequency. Load/disturbance scenarios must be started explicitly in the UI or API.

OCPP EVSE total and session energy also use elapsed simulation seconds, so
changing polling frequency or pausing does not inflate the counters. Resetting
the simulation clock reinitializes the elapsed-time measurement. CSMS accepts
both `sampledValue` and `sampled_value`, selects energy/power by measurand, and
converts kWh/kW to Wh/W. Missing or malformed samples retain the last valid reading.
OCPP demonstration scenarios are initially stopped; explicitly Start a scenario
to simulate charging, rejection or a fault instead of running conflicting demos
automatically with the model.

- **Protocols**: MQTT, Modbus TCP, OCPP (SunSpec/OPC UA coming next).
- **Models**: OCPP 1.6 EVSE + CSMS twins, Siemens VersiCharge AC Modbus EVSE,
  generic three-phase energy meters, a Socomec DIRIS A-10 Modbus energy meter,
  and a Schneider Electric PowerLogic PM5560 Modbus power meter.
- **Quickstart**: `profiles/energy_pack/ev_csms_demo.yaml` (OCPP BootNotification/Heartbeat demo).
