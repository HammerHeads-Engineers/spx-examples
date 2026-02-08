# Smart-Building Pack (BMS)

Smart-building BMS/BAS demo pack covering HVAC, lighting, safety, energy, and telemetry
across MQTT, LwM2M/CoAP, HTTP, Modbus TCP, OPC UA, KNX, Matter, and BACnet. Use it
to validate multi-protocol integrations, test gateways, or build demo dashboards.

## What is inside

- Protocols: MQTT, LwM2M/CoAP, HTTP, Modbus TCP, OPC UA, KNX, Matter, BACnet.
- Core scenarios: room telemetry, HVAC control, lighting automation, safety/security,
  weather backhaul, and home/IoT bridge flows.

### Model highlights

- HVAC and energy
  - BMS controller (OPC UA): `library/domains/iot/generic/bms_controller__opcua.yaml`
  - Flexit Nordic HVAC (BACnet): `library/domains/iot/generic/hvac_flexit_nordic__bacnet.yaml`
  - Thermal controller (Modbus): `library/domains/thermal_controllers/generic/thermal_controller__modbus.yaml`
  - Energy meter iEM3000 (Modbus): `library/domains/iot/generic/energy_meter_iem3000__modbus.yaml`
  - Socomec DIRIS A-40 power meter (Modbus): `library/domains/iot/socomec/diris_a40__modbus.yaml`
- Lighting
  - Lighting panel (OPC UA): `library/domains/iot/generic/lighting_panel__opcua.yaml`
  - Lighting zone (KNX): `library/domains/iot/generic/lighting_zone__knx.yaml`
  - ABB switch actuator (KNX): `library/domains/iot/abb/abb_sa_s12_16_5_1__knx.yaml`
  - ABB cover actuator (KNX): `library/domains/iot/abb/abb_jra_s4_230_5_1__knx.yaml`
- Room and IAQ
  - Room controller (KNX): `library/domains/iot/generic/room_controller__knx.yaml`
  - Presence detector (KNX): `library/domains/iot/theben/theronda_p360__knx.yaml`
  - Environment sensors (MQTT/LwM2M): `library/domains/iot/generic/environment_sensor__mqtt.yaml`,
    `library/domains/iot/generic/environment_sensor__lwm2m.yaml`
  - Air quality station (HTTP): `library/domains/iot/generic/air_quality_station__http.yaml`
- Safety and security
  - Fire alarm panel (BACnet): `library/domains/iot/generic/fire_alarm_panel__bacnet.yaml`
  - Security access controller (BACnet): `library/domains/iot/generic/security_access_controller__bacnet.yaml`
- Weather and Matter
  - Weather forecast (HTTP): `library/domains/weather/weather_forecast__http.yaml`
  - Weather gateway (MQTT): `library/domains/weather/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml`
  - Thermostat (Matter): `library/domains/iot/generic/thermostat__matter.yaml`
  - Smart plug (Matter): `library/domains/iot/generic/smart_plug__matter.yaml`

## Quickstart

- Profile: `profiles/smart_building_pack/bms_quickstart.yaml`
- Services enabled by the profile: MQTT, Modbus, BACnet, LwM2M, HTTP, OPC UA, KNX,
  Home Assistant bridge, Matter server.
- When selecting this pack in the installer, Home Assistant is installed as well.
  Access it at `http://localhost:8123` (login: `admin`, password: `spx-examples`).
- Use the installer wizard (`./spx-install.sh`) or generate non-interactively:
  `python -m installer generate --packages smart_building_pack --profile-ids bms_quickstart`
- Integration tests: `poetry run pytest tests/packs/smart_building_pack/integration`
- Notebook: `examples/packs/smart_building_pack/smart_building_pack_weather_gateway.ipynb`

## Connection matrix

| Service | Ports | Notes |
| --- | --- | --- |
| mqtt_broker | 1883/tcp | MQTT env sensors and weather gateway |
| lwm2m_server | 5683/udp, 5684/udp, 8080/tcp | LwM2M env sensor + management UI |
| http_gateway | 8091/tcp, 8092/tcp | Weather forecast + air quality feeds |
| modbus_tcp_gateway | 502/tcp | Thermal controller via gateway; per-model Modbus ports live in YAML (e.g. iEM3000 uses 5023) |
| bacnet_gateway | 47808/udp, 47818/udp, 47828/udp | Flexit HVAC, security, fire panel |
| opcua_server | 4843/tcp, 4844/tcp | BMS controller + lighting panel endpoints |
| knx_gateway | 3671/udp, 6720/tcp | KNX/IP tunneling + TCP interface |
| homeassistant_bridge | 8123/tcp | Home Assistant UI and device bridge |
| matter_server | 5580/tcp | Matter API/WebSocket for HA |

### Endpoint examples

- OPC UA BMS controller: `opc.tcp://localhost:4843/spx/bms-controller`
- OPC UA lighting panel: `opc.tcp://localhost:4844/spx/lighting-panel`
- Matter server WebSocket: `ws://localhost:5580/ws`

## Tests

- Unit and catalog checks: `tests/packs/smart_building_pack/unit`
- Integration checks: `tests/packs/smart_building_pack/integration`
