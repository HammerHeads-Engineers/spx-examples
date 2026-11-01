# Industrial Pack (Industry 4.0)

OPC UA/Modbus/MQTT/HTTP-oriented kit for line automation, process control and
factory monitoring. The present iteration links the models we already maintain;
additional Redfish device twins can land alongside.

## Start here

| Item | What to use |
| --- | --- |
| First SPX result | [Temperature tutorial](../../../examples/README.md#first-success-temperature-telemetry) |
| Protocol-free behavior | `Process.ThermalController.Advanced`: `setpoint`, `temperature`, `heating_power` |
| Process-cell preset | [Process-cell profile](../../../profiles/industrial_iiot_pack/process_cell_quickstart.yaml) |
| Coupled Modbus demo | [PLC/VFD/meter profile](../../../profiles/industrial_iiot_pack/modbus_master_plc_demo.yaml) |
| Live workflow | [MCP/runtime guide](../../../docs/RUNTIME_WORKFLOW.md) |

Use a compatible SPX test server with its declared model helpers available. An
agent can register the advanced thermal model, start a uniquely named instance
and observe the response to a setpoint change. The legacy public attributes above
are intentionally retained; do not rename them to follow new-model conventions.
Success means `RUNNING` plus the observed behavior, not closed-loop protocol proof.
Stop/delete only the example objects when finished.

Profiles select models/services rather than deploying them. Ports below are
prepared-deployment defaults; inspect actual instance endpoints/host bindings.
The coupled Modbus demo also needs its slave devices and explicit read/write tests.

Legacy `modbus_tcp` twins (thermal/PID controllers, VFD, pressure transmitter,
I/O module) expose `modbus_host` and `modbus_port` provisioning parameters.
The default container port remains 502 for compatibility with the shared gateway.
For a dedicated instance endpoint, choose a container port from 5020–5120 and
connect the client to its published host port listed in `bundle.json` (for
example, container 5020 may be published as host 15020). Unit IDs remain
automatically allocated by the legacy runtime.

MQTT models use the bundled `mosquitto-server:1883` by default. Set
`mqtt_broker_host`, `mqtt_broker_port`, and `mqtt_topic_prefix` when provisioning
an external broker or multiple instances. Demo scenarios are opt-in: start them
explicitly from the UI or API. AGV motion/battery and line counts use elapsed
simulation time; their public `cycle_time_s` remains the reference step for slew tuning.
The AGV steers toward its waypoint and limits each movement step to the remaining
distance, including after scenario overrides end. Set `k__autonomous_navigation`
to `false` (MQTT `command/autonomous_navigation`) to use the legacy manual
`heading_deg` control instead.

- **Protocols**: Modbus TCP, MQTT, HTTP, SCPI, OPC UA.
- **Models**: motion control, process instrumentation, QA instrumentation, vendor-specific controllers (Eurotherm, Siemens, Schneider Electric, WAGO, APC Rack PDU).
- **OPC UA**: process-focused twins:
  * `Process.ProcessCell.OpcUa` – thermal/pressure loop mirroring AsyncUA tests.
  * `Process.Workcell.OpcUa` – robotic/machining cell with cycle measurements and alarms.
  * `Process.PackagingLine.OpcUa` – packaging line with wrapper, queue and alarms.
  * `Process.ProcessCell.SiemensS7_1500.OpcUa` – vendor-specific process cell endpoint.
- **Quickstarts**:
  * `profiles/industrial_iiot_pack/process_cell_quickstart.yaml`
  * `profiles/industrial_iiot_pack/modbus_master_plc_demo.yaml` - generic PLC-style `modbus_master` demo that supervises an Altivar 320 VFD and an iEM3000 energy meter over direct Modbus TCP slave endpoints.

## Connection matrix

| Service | Ports | Notes |
| --- | --- | --- |
| modbus_tcp_gateway | 502/tcp | For models using `communication.modbus_tcp`. Models using `communication.modbus_slave` expose their own ports defined in YAML (e.g. Eurotherm, G120C, WAGO). |
| mqtt_broker | 1883/tcp | MQTT telemetry (line counter, condition monitor, AGV). |
| http_gateway | 8091/tcp, 8092/tcp | HTTP feeds (air quality). Some models expose their own HTTP endpoints (e.g. vision station on 8093). |
| scpi_tcp_stack | 5025/tcp, 5026/tcp | SCPI listeners for bench instruments. |
| opcua_server | 4840-4845/tcp | OPC UA endpoints listed below. |

### Endpoint examples

- OPC UA process cell: `opc.tcp://localhost:4840/spx/process-cell`
- OPC UA workcell: `opc.tcp://localhost:4841/spx/workcell`
- OPC UA packaging line: `opc.tcp://localhost:4842/spx/packaging-line`
- OPC UA S7-1500 process cell: `opc.tcp://localhost:4845/spx/s7-1500/process-cell` (anonymous or `operator`/`changeme`)
