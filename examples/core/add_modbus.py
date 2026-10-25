# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

import os
import time
import yaml

import spx_python

product_key = os.environ.get("SPX_PRODUCT_KEY")
if product_key is None:
    raise ValueError("Environment variable SPX_PRODUCT_KEY is required.")
# Initialize client to connect to local server
client = spx_python.init(
    address="http://localhost:8000",
    product_key=product_key  # required env var
)

# 2) Define the model (PT100-like sensor) + Modbus TCP mapping
pt_100_yaml = '''
attributes:
  temperature: 25.0
  sensor_fault: 0
actions:
  - { ramp: $in(temperature), stop_value: 150, duration: 5, type: overshoot, overshoot: 5}
  - { noise: $out(temperature), std: 0.01, mode: proportional}
communication:
  - modbus_tcp:
      mapping:
        temperature: {address: [0,1], group: h_r, type: uint_32}
        sensor_fault: { address: [4,4], group: c_o, type: uint_16 }
'''


def create_instance(client, model_name, instance_name, overrides=None):
    """Helper to create an instance with optional attribute overrides."""
    client["instances"][instance_name] = model_name
    if overrides:
        inst = client["instances"][instance_name]
        for attr_path, value in overrides.items():
            inst.put_attr(attr_path, value)
    return client["instances"][instance_name]


# Parse YAML and register the model
model_def = yaml.safe_load(pt_100_yaml)
client["models"]["pt_100_modbus"] = model_def

inst = create_instance(client, "pt_100_modbus", "pt100_modbus_1", overrides={"communication/modbus_tcp/id": 2})

from modbus_tk import modbus_tcp
from modbus_tk import defines as c


class SUTSensor:
    """Software Under Test (SUT): thin Modbus TCP wrapper for reading measurements.
    Hides protocol details from the test/plotting logic.
    """
    def __init__(self, host="127.0.0.1", port=502, unit=1, scale=1.0, timeout=2.0):
        self.host = host
        self.port = port
        self.unit = unit
        self.scale = scale
        self.timeout = timeout
        self._mb = None

    def connect(self):
        """Create master and validate connectivity with a lightweight probe."""
        self._mb = modbus_tcp.TcpMaster(host=self.host, port=self.port)
        self._mb.set_timeout(self.timeout)
        # # Optional: do a tiny probe read; if server rejects, this will raise.
        # try:
        #     # A harmless probe: read 0 registers (some stacks allow count=0, others do not).
        #     # If your server dislikes count=0, you can skip the probe or read a known-safe address.
        #     self._mb.execute(self.unit, c.READ_COILS, 0, 1)
        # except Exception as e:
        #     raise RuntimeError(f"Could not connect to Modbus server at {self.host}:{self.port} (unit {self.unit})") from e

    @staticmethod
    def _u32_from_two_u16_be(regs):
        """Combine two 16-bit registers into one 32-bit unsigned integer (Big Endian)."""
        if len(regs) != 2:
            raise ValueError(f"Expected 2 registers, got {len(regs)}")
        return ((regs[0] & 0xFFFF) << 16) | (regs[1] & 0xFFFF)

    def read_temperature_and_fault(self):
        """Temperature from HR 0–1 (uint32 Big Endian), fault flag from coil 4 (0/1)."""
        if self._mb is None:
            raise RuntimeError("Modbus master not connected. Call connect() first.")

        # Read temperature (two 16-bit holding registers)
        hr = self._mb.execute(self.unit, c.READ_HOLDING_REGISTERS, 0, 2)
        raw_u32 = self._u32_from_two_u16_be(hr)
        temp = raw_u32 / self.scale  # adjust scaling to your model if needed

        # Read fault flag (coil 4)
        coils = self._mb.execute(self.unit, c.READ_COILS, 4, 1)
        fault = int(bool(coils[0]))

        return temp, fault

    def close(self):
        """modbus_tk masters close automatically on GC; nothing required here."""
        self._mb = None


# 3) SUT: Modbus client (modbus_tk)
sensor = SUTSensor(host="127.0.0.1", port=502, unit=2, scale=1.0, timeout=2.0)


temperatures, fault_flags, timestamps = [], [], []

# 4) Start model, capture synchronously (server scheduler advances time)
inst.reset()
inst.start()
sensor.connect()
try:
    for i in range(150):  # ~5 seconds at 0.1 s interval
        temp, fault = sensor.read_temperature_and_fault()
        temperatures.append(temp)
        fault_flags.append(fault)
        timestamps.append(i * 0.1)
        print(f"time: {i*0.1:.1f}s  temp: {temp:.3f}C  fault: {fault}")
        time.sleep(0.1)  # optional: align with dt for easier inspection
finally:
    inst.stop()
    sensor.close()

# 5) Plot results (Plotly)
import plotly.graph_objects as go
from plotly.subplots import make_subplots

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.08,
    row_heights=[0.65, 0.35],
    subplot_titles=("Temperature (HR 0–1)", "Sensor Fault (coil 4)")
)

# Top: temperature as a line
fig.add_trace(
    go.Scatter(x=timestamps, y=temperatures, mode='lines', name='Temperature'),
    row=1, col=1
)

# Bottom: fault flag as a step line (0/1)
fig.add_trace(
    go.Scatter(x=timestamps, y=fault_flags, mode='lines', line_shape='hv', name='Fault Flag'),
    row=2, col=1
)

fig.update_yaxes(title_text="Temperature", row=1, col=1)
fig.update_yaxes(title_text="Fault Flag", row=2, col=1, range=[-0.1, 1.1], dtick=1)
fig.update_xaxes(title_text="Time (s)", row=2, col=1)

fig.update_layout(
    title="Modbus PT100 Readout",
    template="plotly_white",
    showlegend=True,
    height=500
)

# Save interactive HTML (works in headless/CI)
out_html = os.path.join(os.path.dirname(__file__), 'add_modbus.html')
try:
    fig.write_html(out_html, include_plotlyjs='cdn', full_html=True)
    print(f"Saved interactive Plotly chart to: {out_html}")
except Exception as e:
    print(f"Failed to write HTML chart: {e}")

# # Try to display if a renderer is available
# try:
#     fig.show()
# except Exception:
#     pass
