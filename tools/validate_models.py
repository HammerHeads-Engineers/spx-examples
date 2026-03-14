#!/usr/bin/env python3
"""Lightweight validation for model YAML files and catalog references."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import guard for CLI use
    raise SystemExit(
        "Missing dependency: pyyaml. Install with 'poetry install --with dev'."
    ) from exc

MODEL_NAME_RE = re.compile(r"^[a-z0-9_]+$")
TAXONOMY_NAME_RE = re.compile(r"^[a-z0-9_]+$")
ALLOWED_DOMAIN_GROUPS = {
    "building",
    "environment",
    "industrial",
    "energy",
    "lab",
}


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def add(self, message: str) -> None:
        self.errors.append(message)

    def extend(self, messages: list[str]) -> None:
        self.errors.extend(messages)

    def ok(self) -> bool:
        return not self.errors


def load_yaml(path: Path, result: ValidationResult) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except Exception as exc:  # pragma: no cover - error path
        result.add(f"{path}: failed to parse YAML ({exc})")
        return None


def validate_model_file(path: Path, data: object, result: ValidationResult) -> None:
    if not isinstance(data, dict):
        result.add(f"{path}: top-level YAML must be a mapping")
        return

    if not MODEL_NAME_RE.match(path.stem):
        result.add(f"{path}: file name must be lower_snake_case")

    name = data.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            result.add(f"{path}: empty 'name'")
        elif not MODEL_NAME_RE.match(name):
            result.add(f"{path}: name '{name}' must be lower_snake_case")

    description = data.get("description")
    if description is not None:
        if not isinstance(description, str) or not description.strip():
            result.add(f"{path}: empty 'description'")

    attributes = data.get("attributes")
    if not isinstance(attributes, dict):
        result.add(f"{path}: missing or invalid 'attributes' mapping")

    actions = data.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            result.add(f"{path}: 'actions' must be a list")
        else:
            for idx, action in enumerate(actions):
                if not isinstance(action, dict):
                    result.add(f"{path}: actions[{idx}] must be a mapping")

    conditions = data.get("conditions")
    if conditions is not None:
        if not isinstance(conditions, list):
            result.add(f"{path}: 'conditions' must be a list")
        else:
            for idx, condition in enumerate(conditions):
                if not isinstance(condition, dict):
                    result.add(f"{path}: conditions[{idx}] must be a mapping")

    communication = data.get("communication")
    if communication is not None:
        if isinstance(communication, list):
            for idx, block in enumerate(communication):
                if not isinstance(block, dict) or not block:
                    result.add(
                        f"{path}: communication[{idx}] must be a non-empty mapping"
                    )
        elif isinstance(communication, dict):
            if not communication:
                result.add(f"{path}: 'communication' must be a non-empty mapping")
        else:
            result.add(f"{path}: 'communication' must be a list or mapping")

    scenarios = data.get("scenarios")
    if scenarios is None:
        return
    if not isinstance(scenarios, dict):
        result.add(f"{path}: 'scenarios' must be a mapping")
        return

    for scenario_name, scenario_def in scenarios.items():
        if not isinstance(scenario_name, str) or not scenario_name.strip():
            result.add(f"{path}: scenario key must be a non-empty string")
            continue
        if not isinstance(scenario_def, dict):
            result.add(f"{path}: scenario '{scenario_name}' must be a mapping")
            continue

        display_name = scenario_def.get("display_name")
        if display_name is not None:
            if not isinstance(display_name, str) or not display_name.strip():
                result.add(f"{path}: scenario '{scenario_name}' has empty display_name")

        scenario_description = scenario_def.get("description")
        if scenario_description is not None:
            if (
                not isinstance(scenario_description, str)
                or not scenario_description.strip()
            ):
                result.add(f"{path}: scenario '{scenario_name}' has empty description")

        overrides = scenario_def.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            result.add(
                f"{path}: scenario '{scenario_name}' overrides must be a mapping"
            )

        scenario_actions = scenario_def.get("actions")
        if scenario_actions is not None:
            if not isinstance(scenario_actions, list):
                result.add(f"{path}: scenario '{scenario_name}' actions must be a list")
            else:
                for idx, action in enumerate(scenario_actions):
                    if not isinstance(action, dict):
                        result.add(
                            f"{path}: scenario '{scenario_name}' actions[{idx}] must be a mapping"
                        )

        scenario_conditions = scenario_def.get("conditions")
        if scenario_conditions is not None:
            if not isinstance(scenario_conditions, list):
                result.add(
                    f"{path}: scenario '{scenario_name}' conditions must be a list"
                )
            else:
                for idx, condition in enumerate(scenario_conditions):
                    if not isinstance(condition, dict):
                        result.add(
                            f"{path}: scenario '{scenario_name}' conditions[{idx}] must be a mapping"
                        )


def validate_model_catalog(root: Path, result: ValidationResult) -> None:
    catalog_path = root / "library" / "catalog" / "models.yaml"
    if not catalog_path.exists():
        result.add(f"{catalog_path}: missing catalog file")
        return

    data = load_yaml(catalog_path, result)
    if not isinstance(data, dict):
        result.add(f"{catalog_path}: top-level YAML must be a mapping")
        return

    models = data.get("models")
    if not isinstance(models, list):
        result.add(f"{catalog_path}: 'models' must be a list")
        return

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for entry in models:
        if not isinstance(entry, dict):
            result.add(f"{catalog_path}: each model entry must be a mapping")
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            result.add(f"{catalog_path}: model entry missing 'id'")
        elif entry_id in seen_ids:
            result.add(f"{catalog_path}: duplicate model id '{entry_id}'")
        else:
            seen_ids.add(entry_id)

        entry_name = entry.get("name")
        if not isinstance(entry_name, str) or not entry_name.strip():
            result.add(f"{catalog_path}: model entry missing 'name'")

        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            result.add(f"{catalog_path}: model entry missing 'path'")
            continue
        if path_value in seen_paths:
            result.add(f"{catalog_path}: duplicate model path '{path_value}'")
        else:
            seen_paths.add(path_value)
        model_path = root / path_value
        if not model_path.exists():
            result.add(f"{catalog_path}: model path not found: {path_value}")

        domain = entry.get("domain")
        if not isinstance(domain, str) or not domain.strip():
            result.add(f"{catalog_path}: model entry missing 'domain'")

        domain_group = entry.get("domain_group")
        if not isinstance(domain_group, str) or not domain_group.strip():
            result.add(
                f"{catalog_path}: model entry '{entry_id}' missing 'domain_group'"
            )
        elif domain_group not in ALLOWED_DOMAIN_GROUPS:
            result.add(
                f"{catalog_path}: model entry '{entry_id}' has invalid domain_group '{domain_group}'"
            )

        device_class = entry.get("device_class")
        if not isinstance(device_class, str) or not device_class.strip():
            result.add(
                f"{catalog_path}: model entry '{entry_id}' missing 'device_class'"
            )
        elif not TAXONOMY_NAME_RE.match(device_class):
            result.add(
                f"{catalog_path}: model entry '{entry_id}' has invalid device_class '{device_class}'"
            )

        vendor = entry.get("vendor")
        if not isinstance(vendor, str) or not vendor.strip():
            result.add(f"{catalog_path}: model entry '{entry_id}' missing 'vendor'")
        elif not TAXONOMY_NAME_RE.match(vendor):
            result.add(
                f"{catalog_path}: model entry '{entry_id}' has invalid vendor '{vendor}'"
            )

        for list_key in ("protocols", "services", "packages", "profiles"):
            value = entry.get(list_key)
            if not isinstance(value, list):
                result.add(
                    f"{catalog_path}: model entry '{entry_id}' missing '{list_key}' list"
                )


def validate_models(root: Path) -> ValidationResult:
    result = ValidationResult()
    model_root = root / "library" / "domains"
    if not model_root.exists():
        result.add(f"{model_root}: missing model directory")
        return result

    for path in sorted(model_root.rglob("*.yaml")):
        data = load_yaml(path, result)
        if data is None:
            continue
        validate_model_file(path, data, result)

    validate_model_catalog(root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SPX model YAML files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: project root)",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    result = validate_models(root)
    if result.ok():
        print("Model validation passed.")
        return 0

    print("Model validation failed:")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
