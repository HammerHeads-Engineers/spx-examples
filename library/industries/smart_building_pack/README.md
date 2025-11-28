# Smart-Building Pack (BMS)

Curated HVAC/room automation bundle covering multi-protocol sensors, controllers,
and supporting services. Use it to bootstrap BMS-style demos, KNX/BACnet bridges,
Home Assistant integrations, or OPC UA-based BAS overlays.

- **Protocols**: MQTT, LwM2M/CoAP, HTTP, Modbus TCP, OPC UA, KNX, Matter (python-matter-server).
- **Models**: environmental telemetry nodes, HVAC controllers, virtual weather feeds,
  OPC UA twins for the central BMS controller i panelu oświetlenia,
  a także KNX room controller / lighting zone do testów KNX/IP (tunneling 3671) i urządzenia Matter
  (np. termostat oraz przekaźnik OnOff widoczny w Home Assistant po sparowaniu).
- **Quickstart**: see `profiles/smart_building_pack/bms_quickstart.yaml`.
