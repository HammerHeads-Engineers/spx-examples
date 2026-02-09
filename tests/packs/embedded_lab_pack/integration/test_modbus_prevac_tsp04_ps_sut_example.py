# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import tests.shared.integration.modbus_prevac_tsp04_ps_sut_example as shared_prevac


MODEL_KEY = "embedded_lab_pack__prevac_tsp04_ps"
INSTANCE_KEY = "spx_prevac_tsp04_ps"


class TestModbusPrevacTSP04PSPackIntegration(
    shared_prevac.TestModbusPrevacTSP04PSExampleIntegration
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
