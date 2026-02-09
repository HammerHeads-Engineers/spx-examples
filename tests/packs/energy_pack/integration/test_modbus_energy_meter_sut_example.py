# SPDX-License-Identifier: MIT

import tests.shared.integration.modbus_energy_meter_sut_example as shared_meter


class TestModbusEnergyMeterSUTExampleIntegration(
    shared_meter.TestModbusEnergyMeterSUTExampleIntegration
):
    """Run the shared Socomec DIRIS A-40 suite for the energy pack."""
