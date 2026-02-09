# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import tests.shared.integration.modbus_prevac_m1600pdc_ps_sut_example as shared_prevac


MODEL_KEY = "embedded_lab_pack__prevac_m1600pdc_ps"
INSTANCE_KEY = "spx_prevac_m1600pdc_ps"


class TestModbusPrevacM1600PDCPSPackIntegration(
    shared_prevac.TestModbusPrevacM1600PDCPSExampleIntegration
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._client.update_model_key(shared_prevac.MODEL_KEY, MODEL_KEY)
        cls._client.update_instance_key(shared_prevac.INSTANCE_KEY, INSTANCE_KEY)

    def setUp(self):
        if shared_prevac.ModbusTcpClient is None:  # pragma: no cover - dependency missing
            self.skipTest("pymodbus not available")
        super().setUp()
