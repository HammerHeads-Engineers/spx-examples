# Industrial Pack (Industry 4.0)

OPC UA/Modbus/MQTT/HTTP-oriented kit for line automation, process control and
factory monitoring. The present iteration links the models we already maintain;
additional Redfish device twins can land alongside.

- **Protocols**: Modbus TCP, MQTT, HTTP, SCPI, OPC UA.
- **Models**: motion control, process instrumentation, QA instrumentation, vendor-specific controllers (ABB M1M, Eurotherm, Siemens, WAGO).
- **OPC UA**: process-focused twins:
  * `Process.ProcessCell.OpcUa` – thermal/pressure loop mirroring AsyncUA tests.
  * `Process.Workcell.OpcUa` – robotic/machining gniazdo z pomiarem cykli i alarmami.
  * `Process.PackagingLine.OpcUa` – linia pakująca z wrapperem, kolejką i alarmami.
  * `Process.ProcessCell.SiemensS7_1500.OpcUa` – vendor-specific process cell endpoint.
- **Quickstart**: `profiles/industrial_iiot_pack/process_cell_quickstart.yaml`.

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
