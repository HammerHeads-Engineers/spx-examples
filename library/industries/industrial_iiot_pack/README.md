# Industrial / IIoT Pack

OPC UA/Modbus/MQTT/SNMP-oriented kit for line automation, process control and
factory monitoring. The present iteration links the models we already maintain;
additional Redfish/SNMP device twins can land alongside.

- **Protocols**: Modbus TCP, MQTT, BLE (monitoring), SCPI (QA labs), OPC UA.
- **Models**: motion control, process instrumentation, QA instrumentation.
- **OPC UA**: process-focused twins:
  * `Process.ProcessCell.OpcUa` – thermal/pressure loop mirroring AsyncUA tests.
  * `Process.Workcell.OpcUa` – robotic/machining gniazdo z pomiarem cykli i alarmami.
  * `Process.PackagingLine.OpcUa` – linia pakująca z wrapperem, kolejką i alarmami.
- **Quickstart**: `profiles/industrial_iiot_pack/opcua_line_quickstart.yaml`.
