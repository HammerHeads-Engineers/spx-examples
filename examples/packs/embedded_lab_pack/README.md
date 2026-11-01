# Embedded Lab Pack Examples

Use the [temperature tutorial](../../README.md#first-success-temperature-telemetry)
for a first result without adapters. The [pack guide](../../../library/industries/embedded_lab_pack/README.md)
links SCPI, MQTT and LwM2M selections and their requirements.

[BLE temperature script](load_ble_temperature_sensor.py) is a **preview-only**
example. It needs a separately supported BLE adapter environment and a reachable
adapter HTTP endpoint; the current stable catalog omits this model pending BLE QA.
Inspect its endpoint, credential and instance assumptions before running it.
Do not use it as the first-install or stable-catalog acceptance test.
