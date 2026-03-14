"""Load BLE models from YAML and spin up an instance for quick inspection."""

import argparse
import os
import pprint
from pathlib import Path

import spx_python
import yaml

MODEL_PATHS = {
    "ble_temperature_sensor": Path(
        "library/domains/lab/sensor/generic/temperature_sensor__ble_gatt.yaml"
    ),
    "ble_vital_signs_monitor": Path(
        "library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a BLE model from YAML, register it, and start an instance."
    )
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_PATHS),
        default="ble_temperature_sensor",
        help="Registered model key to load (default: %(default)s).",
    )
    parser.add_argument(
        "--instance",
        help="Instance name to create (default: <model>_instance).",
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="spx server address (default: %(default)s).",
    )
    return parser.parse_args()


def init_client(address: str):
    product_key = os.environ.get("SPX_PRODUCT_KEY")
    if product_key is None:
        raise ValueError("Environment variable SPX_PRODUCT_KEY is required.")
    return spx_python.init(address=address, product_key=product_key)


def load_model_definition(project_root: Path, model_key: str):
    yaml_path = project_root / MODEL_PATHS[model_key]
    with yaml_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    return config, yaml_path


def create_instance(client, model_name, instance_name, overrides=None):
    """Helper to create an instance with optional attribute overrides."""
    client["instances"][instance_name] = model_name
    if overrides:
        inst = client["instances"][instance_name]
        for attr_path, value in overrides.items():
            inst.put_attr(attr_path, value)
    return client["instances"][instance_name]


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    client = init_client(args.server)

    model_def, yaml_path = load_model_definition(project_root, args.model)
    instance_name = args.instance or f"{args.model}_instance"

    print(f"Loaded configuration for {args.model!r} from {yaml_path}:")
    pprint.pprint(model_def)

    client["models"][args.model] = model_def
    print(f"Registered model {args.model!r} with the server.")

    inst = create_instance(client, args.model, instance_name, overrides=None)
    print(f"Created instance {instance_name!r}: {inst}")
    inst.start()

    pprint.pprint(inst["logs"].tail())


if __name__ == "__main__":
    main()
