# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import tests.shared.integration.modbus_prevac_tsp04_ps_sut_example as shared_prevac


class TestModbusPrevacTSP04PSPackIntegration(
    shared_prevac.TestModbusPrevacTSP04PSExampleIntegration
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        if shared_prevac.ModbusTcpClient is None:  # pragma: no cover - dependency missing
            self.skipTest("pymodbus not available")
        super().setUp()
