# ASCII/SCPI Example

This example demonstrates a minimal ASCII/SCPI stack with:
- Python simulators for a bench power supply (PSU) and a digital multimeter (DMM).
- SPX model files that expose the same command sets.
- Thin ASCII transport helper + scripts that use the SPX Python client.

## Layout
- `models/`: SPX model YAML/JSON for the PSU and DMM examples.
- `sim/`: Python simulators that emulate SCPI-over-TCP (and optional serial).
- `spx/`: ASCII transport helper and config template.
- `scripts/`: SPX client scripts that talk to the running SPX ASCII stack.

## Run the simulators

Power supply simulator (TCP 5025):
```bash
python -m examples.ascii_scpi.sim.psu_sim --host 127.0.0.1 --port 5025
```

Digital multimeter simulator (TCP 5026):
```bash
python -m examples.ascii_scpi.sim.dmm_sim --host 127.0.0.1 --port 5026
```

Optional serial mode (requires `pyserial`):
```bash
python -m examples.ascii_scpi.sim.psu_sim --serial /dev/ttyUSB0 --baud 9600 --terminator "\r\n"
```

## Run against SPX

1) Start the SPX stack (server must be reachable at `SPX_BASE_URL`).
2) Export a product key:
```bash
export SPX_PRODUCT_KEY=your_key
export SPX_BASE_URL=http://localhost:8000
```
3) Use the scripts (they load the example models into SPX and talk to the ASCII port):
```bash
python examples/ascii_scpi/scripts/psu_set_voltage.py --voltage 12.0 --current 0.5
python examples/ascii_scpi/scripts/psu_toggle_output.py --state on
python examples/ascii_scpi/scripts/dmm_read_voltage.py --range 10
```

## Command mappings

PSU (example model + simulator):
- `*IDN?` -> `idn`
- `SOUR:VOLT <v>` -> `k__voltage_set_v`
- `SOUR:CURR <i>` -> `k__current_set_a`
- `MEAS:VOLT?` -> `voltage_readback_v`
- `MEAS:CURR?` -> `current_readback_a`
- `OUTP ON|OFF` -> `k__output_state`
- `SYST:ERR?` -> error queue (default `0,"No error"`)

DMM (example model + simulator):
- `*IDN?` -> `idn`
- `CONF:VOLT:DC [range]` -> `k__mode`, `k__range_v`
- `MEAS:VOLT:DC?` -> `voltage_readback_v`
- `MEAS:RES?` -> `resistance_readback_ohm`
- `READ?` -> `readback_value` (mode-dependent)
- `SYST:ERR?` -> error queue (default `0,"No error"`)

## Pitfalls
- **Terminators**: SCPI often expects `\n` or `\r\n`. Match the simulator/transport terminator.
- **Spacing**: `SOUR:VOLT 5.0` (single space) is the safest parse target.
- **Numeric format**: Stick to `.` decimal separators (avoid locale commas).
- **Timeouts**: Short timeouts make retries visible; adjust in `spx/config.yaml`.

## References
- [Rigol DP800 Programming Guide](https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-03a1/1/-/-/-/-/DP800%20Programming%20Guide.pdf)
- [Rigol DM3000 Series Programming Guide (DM3068)](https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-1160/1/-/-/-/-/DM3068%20Programming%20Guide.zip)
