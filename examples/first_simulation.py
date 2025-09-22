# This example defines a PT100-like sensor model with composite actions
# (ramp, noise). Internal temperature is driven by actions; external
# temperature can include noise without affecting internal logic.

import os
import spx_python
import yaml

product_key = os.environ.get("SPX_PRODUCT_KEY")
if product_key is None:
    raise ValueError("Environment variable SPX_PRODUCT_KEY is required.")
# Initialize client to connect to local server
client = spx_python.init(
    address="http://localhost:8000",
    product_key=product_key  # required env var
)

# Define PT100 model in YAML
# - ramp action drives internal temperature from 0 to 150C in 5s
# - noise action adds small proportional noise to external temperature
# Note: indentation is significant in YAML
pt_100_yaml = '''
attributes:
  temperature: 0.0
actions:
    - { ramp: $in(temperature), stop_value: 150, duration: 5, type: overshoot, overshoot: 5 }
    - { noise: $out(temperature), std: 0.01, mode: proportional }
'''

# Parse YAML and register the model
model_def = yaml.safe_load(pt_100_yaml)
client["models"]["pt_100"] = model_def
# Create an instance and step it deterministically
client["instances"]["pt100_1"] = "pt_100"
# Access instance, attribute, and action via dictionary-like API
inst = client["instances"]["pt100_1"]
temperature = inst["attributes"]["temperature"]
timer = inst["timer"]

import plotly.graph_objects as go

# # # Create an instance and step it deterministically
# # client["instances"]["pt100_1"] = "pt_100"
# Collect data for plotting
times_collected = []
temps_internal = []
temps_external = []

client.prepare()
for k in range(1, 101):  # simulate ~10 seconds with dt=0.1
    t = k * 0.1
    timer.time = t
    client.run()
    # Read both layers: internal (true state) vs external (noisy presentation)
    print(f"time: {t:.1f}s",
          f"internal: {temperature.internal_value:.3f}C",
          f"external: {temperature.external_value:.3f}C")
    # Store for plotting
    times_collected.append(t)
    temps_internal.append(temperature.internal_value)
    temps_external.append(temperature.external_value)

# Plot results with Plotly
fig = go.Figure()
fig.add_trace(go.Scatter(x=times_collected, y=temps_internal, mode='lines', name='Temperature (internal)'))
fig.add_trace(go.Scatter(x=times_collected, y=temps_external, mode='lines', name='Temperature (external)'))
fig.update_layout(
    title='PT100 Temperature Over Time',
    xaxis_title='Time [s]',
    yaxis_title='Temperature [°C]',
    template='plotly_white',
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
)

# Always save an interactive HTML (works in headless/CI)
out_html = os.path.join(os.path.dirname(__file__), 'first_simulation.html')
try:
    fig.write_html(out_html, include_plotlyjs='cdn', full_html=True)
    print(f"Saved interactive Plotly chart to: {out_html}")
except Exception as e:
    print(f"Failed to write HTML chart: {e}")

# Try to display if a renderer is available (won't fail CI)
try:
    fig.show()
except Exception:
    pass
