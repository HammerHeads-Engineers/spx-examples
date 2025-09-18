# This example defines a PT100-like sensor model with composite actions
# (ramp, noise). Internal temperature is driven by actions; external
# temperature can include noise without affecting internal logic.

import os
import spx_python
import yaml
import matplotlib.pyplot as plt

product_key = os.environ.get("SPX_PRODUCT_KEY")
if product_key is None:
    raise ValueError("Environment variable SPX_PRODUCT_KEY is required.")

client = spx_python.init(
    address="http://localhost:8000",
    product_key=product_key  # required env var
)

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
    # collect for plotting
    times_collected.append(t)
    temps_internal.append(temperature.internal_value)
    temps_external.append(temperature.external_value)


# Plot results with Matplotlib
plt.figure()
plt.plot(times_collected, temps_internal, label='Temperature (internal)')
plt.plot(times_collected, temps_external, label='Temperature (external)')
plt.title('PT100 Temperature Over Time')
plt.xlabel('Time [s]')
plt.ylabel('Temperature [°C]')
plt.legend()
plt.grid(True)
plt.tight_layout()
# Save and show
out_png = os.path.join(os.path.dirname(__file__), 'first_simulation.png')
try:
    plt.savefig(out_png, dpi=120)
    print(f"Saved plot to: {out_png}")
except Exception:
    pass
try:
    plt.show()
except Exception:
    pass
