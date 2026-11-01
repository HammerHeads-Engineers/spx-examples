# Smart Building Pack Examples

First run the [temperature tutorial](../../README.md#first-success-temperature-telemetry).
Then follow the [pack guide](../../../library/industries/smart_building_pack/README.md)
to prepare the intended test instances and services.

[Weather gateway notebook](smart_building_pack_weather_gateway.ipynb) checks the
prepared gateway instance and changes `k__outdoor_temperature_c` /
`k__brightness_lux`. Inspect its setup cells for the exact instance name, API URL
and MQTT assumptions before executing it. The notebook does not install the pack.
Expected result: the selected gateway remains running and exposes the changed
weather state; proving MQTT publication additionally requires a broker/subscriber.
