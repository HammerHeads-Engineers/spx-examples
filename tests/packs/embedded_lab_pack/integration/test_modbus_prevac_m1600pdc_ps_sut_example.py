# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import tests.shared.integration.modbus_prevac_m1600pdc_ps_sut_example as shared_prevac


class TestModbusPrevacM1600PDCPSPackIntegration(
    shared_prevac.TestModbusPrevacM1600PDCPSExampleIntegration
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        if shared_prevac.ModbusTcpClient is None:  # pragma: no cover - dependency missing
            self.skipTest("pymodbus not available")
        super().setUp()
