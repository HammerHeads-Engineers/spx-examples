# Industrial Pack Examples

Start with the [temperature tutorial](../../README.md#first-success-temperature-telemetry)
and [Industrial pack guide](../../../library/industries/industrial_iiot_pack/README.md).

The [Eurotherm setpoint notebook](industrial_pack_eurotherm_setpoints.ipynb) changes
temperature/pressure setpoints on prepared instances. Review its setup cells for
instance names, client connection and endpoint assumptions first. Use a test
environment and inspect the resulting telemetry. A Modbus read/write claim needs
the corresponding transport probe; the notebook does not deploy the devices.
