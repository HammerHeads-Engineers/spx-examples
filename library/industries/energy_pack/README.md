# Energy Pack (e-Mobility & DER)

Foundation for energy-native DER / e-mobility scenarios. Includes OCPP 1.6 charge
point + CSMS twins, Modbus EVSEs, and power-meter telemetry for charging and
power-flow demos.

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
