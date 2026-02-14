# Energy Pack (e-Mobility & DER)

Foundation for DER / EMS / e-mobility scenarios. Now includes an OCPP 1.6 charge
point + CSMS handshake alongside the shared telemetry/controllers already in the
catalog.

- **Protocols**: HTTP, MQTT, Modbus TCP, OCPP (SunSpec/OPC UA coming next).
- **Models**: OCPP 1.6 EVSE + CSMS twins, Siemens VersiCharge AC Modbus EVSE, reusable
  telemetry/controllers for DER, a Socomec DIRIS A-10 Modbus energy meter, and a
  Schneider Electric PowerLogic PM5560 Modbus power meter.
- **Quickstart**: `profiles/energy_pack/ev_csms_demo.yaml` (OCPP BootNotification/Heartbeat demo).
