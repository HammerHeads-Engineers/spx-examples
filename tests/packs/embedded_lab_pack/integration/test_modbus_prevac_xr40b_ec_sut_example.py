# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import tests.shared.integration.modbus_prevac_xr40b_ec_sut_example as shared_prevac


MODEL_KEY = "embedded_lab_pack__prevac_xr40b_ec"
INSTANCE_KEY = "spx_prevac_xr40b_ec"


class TestModbusPrevacXR40BECPackIntegration(
    shared_prevac.TestModbusPrevacXR40BECExampleIntegration
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
