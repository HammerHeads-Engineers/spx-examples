# Smart-Building Pack (BMS)

Smart-building BMS/BAS demo pack covering HVAC, lighting, safety, energy, and telemetry
across MQTT, LwM2M/CoAP, HTTP, Modbus TCP, OPC UA, KNX, Matter, and BACnet. Use it
to validate multi-protocol integrations, test gateways, or build demo dashboards.

## Start here

| Item | What to use |
| --- | --- |
| First SPX result | [Temperature tutorial](../../../examples/README.md#first-success-temperature-telemetry) |
| Protocol-free pack model | `Building.Physics.Generic`: inspect `k__outdoor_temperature_c` and `indoor_temperature_c` |
| Pack selection/preset | [BMS profile](../../../profiles/smart_building_pack/bms_quickstart.yaml) |
| Live workflow | [MCP/runtime guide](../../../docs/RUNTIME_WORKFLOW.md) |
| Notebook | [Weather gateway example](../../../examples/packs/smart_building_pack/README.md), requiring its prepared MQTT instance |

Use a compatible SPX test server with a free instance slot. For the protocol-free
model, ask an agent to find/register `Building.Physics.Generic`, start a uniquely
named instance, inspect its defaults and compare its telemetry after changing an
outdoor input. Success means a `RUNNING` instance and the requested observed change.
Stop/delete only the example objects when finished. Transport checks require the
corresponding services and an explicit protocol probe.

Service names/ports below describe defaults inside a prepared deployment. Profiles
select models/services; they do not install or start those services themselves.
Use actual published host endpoints from your installation or live instance.

MQTT models default to the bundled `mosquitto-server:1883` on the Docker network,
independently of the wizard's host/LAN port binding. Override `mqtt_broker_host`,
`mqtt_broker_port`, and `mqtt_topic_prefix` for an external broker or multiple instances.
Robot-vacuum cleaning, charging, and docking use elapsed simulation seconds;
low battery and a full bin trigger a return to the dock and clear the clean request.

The LwM2M sensor defaults to the bundled `leshan-server`; override
`lwm2m_server_host`/`lwm2m_server_port` for an external server. Set a unique
`lwm2m_endpoint` for each instance. `lwm2m_local_port=0` assigns a free local
CoAP port. Registration and request diagnostics come from the live driver;
the reconnect scenario performs Stop/Start of that same component.

## What is inside

- Protocols: MQTT, LwM2M/CoAP, HTTP, Modbus TCP, OPC UA, KNX, Matter, BACnet.
- Core scenarios: room telemetry, HVAC control, lighting automation, safety/security,
  weather backhaul, and home/IoT bridge flows.

### Model highlights

- HVAC and energy
  - Building Physics: `library/domains/building/physics/generic/building_physics.yaml`
  - BMS controller (OPC UA): `library/domains/building/controller/generic/bms_controller__opcua.yaml`
  - Flexit Nordic HVAC (BACnet): `library/domains/building/controller/generic/hvac_flexit_nordic__bacnet.yaml`
  - Thermal controller (Modbus): `library/domains/industrial/controller/generic/thermal_controller__modbus.yaml`
  - Energy meter iEM3000 (Modbus): `library/domains/energy/meter/schneider/energy_meter_iem3000__modbus.yaml`
  - PV Physics from Lux: `library/domains/energy/pv/generic/pv_physics_lux.yaml`
  - Victron Cerbo GX ESS (Modbus): `library/domains/energy/ess/victron/cerbo_gx_ess__modbus.yaml`
  - Building energy aggregator: `library/domains/energy/controller/generic/building_energy_aggregator.yaml`
  - WAGO PFC200 utility gateway for water/gas pulse meters with weather-driven water demand (MQTT): `library/domains/building/gateway/wago/utility_gateway_wago_pfc200__water_gas_pulse__mqtt.yaml`
  - Easy UPS 3M (Modbus): `library/domains/energy/ups/apc/apc_easy_ups_3m__modbus.yaml`
  - Energy meter PM3200 (Modbus): `library/domains/energy/meter/schneider/schneider_pm3200__modbus.yaml`
  - Energy meter PM5330 (Modbus): `library/domains/energy/meter/schneider/schneider_pm5330__modbus.yaml`
  - PowerLogic PM8000 meter (Modbus): `library/domains/energy/meter/schneider/schneider_powerlogic_pm8000__modbus.yaml`
  - ABB D13 15 energy meter (Modbus): `library/domains/energy/meter/abb/abb_d13_15__modbus.yaml`
  - Energy meter EM4200 (Modbus): `library/domains/energy/meter/schneider/schneider_em4200__modbus.yaml`
  - Siemens PAC3200 power meter (Modbus): `library/domains/energy/meter/siemens/siemens_pac3200__modbus.yaml`
  - Janitza UMG 604-PRO power quality analyzer (Modbus): `library/domains/energy/power_quality_analyzer/janitza/janitza_umg604_pro__modbus.yaml`
  - APC NetShelter Rack PDU 2g (Modbus): `library/domains/energy/rack_pdu/apc/rack_pdu_rpdu2g__modbus.yaml`
  - Energy meter DIRIS A-40 (Modbus): `library/domains/energy/meter/socomec/diris_a40__modbus.yaml`
  - Energy meter EM24 (Modbus): `library/domains/energy/meter/carlo_gavazzi/carlo_gavazzi_em24__modbus.yaml`
  - Energy meter SDM630 (Modbus): `library/domains/energy/meter/eastron/eastron_sdm630__modbus.yaml`
  - Eaton PXM2000 meter (Modbus): `library/domains/energy/meter/eaton/eaton_pxm2000__modbus.yaml`
- Lighting
  - Lighting panel (OPC UA): `library/domains/building/panel/generic/lighting_panel__opcua.yaml`
  - Lighting zone (KNX): `library/domains/building/zone/generic/lighting_zone__knx.yaml`
  - ABB switch actuator (KNX): `library/domains/building/actuator/abb/abb_sa_s12_16_5_1__knx.yaml`
  - ABB cover actuator (KNX): `library/domains/building/actuator/abb/abb_jra_s4_230_5_1__knx.yaml`
- Room and IAQ
  - Room controller (KNX): `library/domains/building/controller/generic/room_controller__knx.yaml`
  - Presence detector (KNX): `library/domains/building/sensor/theben/theronda_p360__knx.yaml`
  - Environment sensors (MQTT/LwM2M): `library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml`,
    `library/domains/environment/sensor/generic/environment_sensor__lwm2m.yaml`
  - Air quality station (HTTP): `library/domains/environment/station/generic/air_quality_station__http.yaml`
- Safety and security
  - Fire alarm panel (BACnet): `library/domains/building/panel/generic/fire_alarm_panel__bacnet.yaml`
  - Security access controller (BACnet): `library/domains/building/controller/generic/security_access_controller__bacnet.yaml`
- Weather
  - Weather forecast (HTTP): `library/domains/environment/feed/generic/weather_forecast__http.yaml`
  - Weather gateway (MQTT): `library/domains/environment/gateway/wago_vaisala/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml`
- Generic devices
  - Thermostat (Matter): `library/domains/building/thermostat/generic/thermostat__matter.yaml`
  - Smart plug (Matter): `library/domains/building/actuator/generic/smart_plug__matter.yaml`
  - Robot vacuum (MQTT): `library/domains/building/actuator/generic/robot_vacuum__mqtt.yaml`

## Quickstart

- The [source pack catalog](../../catalog/industries.yaml) defines recommended
  instances and a smaller auto-start subset. Registration and running-instance
  limits depend on the selected license and deployment.
- The BMS profile declares MQTT, Modbus, BACnet, LwM2M, HTTP, OPC UA, KNX,
  Home Assistant and Matter service requirements. The product installer owns
  deployment, available platform adapters, bindings and credentials.
- To install the product, use the public
  [installation guide](https://docs.simplephysx.com/readme/installation-guide).
  This public checkout contains model/catalog tools and has no installer CLI.
- Run `poetry run pytest tests/packs/smart_building_pack/integration` only in a
  prepared test environment with the required server/services and local credentials.

## Connection matrix

| Service | Ports | Notes |
| --- | --- | --- |
| mqtt_broker | 1883/tcp | MQTT env sensors, weather gateway, WAGO utility meters, and generic robot vacuum |
| lwm2m_server | 5683/udp, 5684/udp, 8080/tcp | LwM2M env sensor + management UI |
| http_gateway | 8091/tcp, 8092/tcp | Weather forecast + air quality feeds |
| modbus_tcp_gateway | 502/tcp | Thermal controller via gateway; per-model Modbus ports live in YAML (e.g. iEM3000 uses 5023, D13 15 uses 5032) |
| bacnet_gateway | 47808/udp, 47818/udp, 47828/udp | Flexit HVAC, security, fire panel |
| opcua_server | 4843/tcp, 4844/tcp | BMS controller + lighting panel endpoints |
| knx_gateway | 3671/udp, 6720/tcp | KNX/IP tunneling + TCP interface |
| homeassistant_bridge | 8123/tcp | Home Assistant UI and device bridge |
| matter_server | 5580/tcp | Matter API/WebSocket for HA |

### Endpoint examples

- OPC UA BMS controller: `opc.tcp://localhost:4843/spx/bms-controller`
- OPC UA lighting panel: `opc.tcp://localhost:4844/spx/lighting-panel`
- Matter server WebSocket: `ws://localhost:5580/ws`

The Matter smart-plug and thermostat models use `matter_server_ws_url`,
`matter_fabric_id`, `matter_node_id` and `matter_endpoint` meta parameters.
Provision the node/endpoint with a device commissioned on that Matter fabric;
the default node `0x1234` is an example identifier. The default WebSocket address
inside a prepared stack is `ws://matter-server:5580/ws`. Keep Matter command
names such as `"On"` and `"Off"` quoted in YAML so they remain protocol names.

## Tests

- Unit and catalog checks: `tests/packs/smart_building_pack/unit`
- Integration checks: `tests/packs/smart_building_pack/integration`
