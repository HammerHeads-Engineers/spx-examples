#!/usr/bin/env python3
"""Lightweight validation for model YAML files and catalog references."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import guard for CLI use
    raise SystemExit(
        "Missing dependency: pyyaml. Install with 'poetry install --with dev --no-root'."
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
MODEL_PATH_RE = re.compile(
    r"^library/domains/(?P<domain>[a-z0-9_]+)/(?P<device_class>[a-z0-9_]+)/(?P<vendor>[a-z0-9_]+)/(?P<file>[a-z0-9_]+\.yaml)$"
)
PACK_INDEX_FIELDS = ("id", "path", "domain_group", "device_class", "vendor")
ALLOWED_PACK_FILES = {"README.md", "SPEC.md", "MODELS.yaml"}


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


def _load_catalog_mapping(
    path: Path, result: ValidationResult
) -> dict[str, Any] | None:
    data = load_yaml(path, result)
    if not isinstance(data, dict):
        result.add(f"{path}: top-level YAML must be a mapping")
        return None
    return data


def validate_domains_catalog(
    root: Path, result: ValidationResult
) -> dict[str, dict[str, Any]]:
    catalog_path = root / "library" / "catalog" / "domains.yaml"
    data = _load_catalog_mapping(catalog_path, result)
    if data is None:
        return {}

    domains = data.get("domains")
    if not isinstance(domains, list):
        result.add(f"{catalog_path}: 'domains' must be a list")
        return {}

    seen_ids: set[str] = set()
    domain_map: dict[str, dict[str, Any]] = {}
    for entry in domains:
        if not isinstance(entry, dict):
            result.add(f"{catalog_path}: each domain entry must be a mapping")
            continue

        domain_id = entry.get("id")
        if not isinstance(domain_id, str) or not domain_id.strip():
            result.add(f"{catalog_path}: domain entry missing 'id'")
            continue
        if domain_id in seen_ids:
            result.add(f"{catalog_path}: duplicate domain id '{domain_id}'")
            continue
        seen_ids.add(domain_id)

        if not TAXONOMY_NAME_RE.match(domain_id):
            result.add(f"{catalog_path}: invalid domain id '{domain_id}'")

        path_value = entry.get("path")
        expected_path = f"library/domains/{domain_id}"
        if not isinstance(path_value, str) or not path_value.strip():
            result.add(f"{catalog_path}: domain '{domain_id}' missing 'path'")
        else:
            if path_value != expected_path:
                result.add(
                    f"{catalog_path}: domain '{domain_id}' should use path '{expected_path}', got '{path_value}'"
                )
            domain_path = root / path_value
            if not domain_path.is_dir():
                result.add(f"{catalog_path}: domain path not found: {path_value}")

        domain_map[domain_id] = entry

    return domain_map


def validate_industries_catalog(
    root: Path, result: ValidationResult
) -> dict[str, dict[str, Any]]:
    catalog_path = root / "library" / "catalog" / "industries.yaml"
    data = _load_catalog_mapping(catalog_path, result)
    if data is None:
        return {}

    industries = data.get("industries")
    if not isinstance(industries, list):
        result.add(f"{catalog_path}: 'industries' must be a list")
        return {}

    seen_ids: set[str] = set()
    industry_map: dict[str, dict[str, Any]] = {}
    for entry in industries:
        if not isinstance(entry, dict):
            result.add(f"{catalog_path}: each industry entry must be a mapping")
            continue

        pack_id = entry.get("id")
        if not isinstance(pack_id, str) or not pack_id.strip():
            result.add(f"{catalog_path}: industry entry missing 'id'")
            continue
        if pack_id in seen_ids:
            result.add(f"{catalog_path}: duplicate industry id '{pack_id}'")
            continue
        seen_ids.add(pack_id)

        path_value = entry.get("path")
        expected_path = f"library/industries/{pack_id}"
        if not isinstance(path_value, str) or not path_value.strip():
            result.add(f"{catalog_path}: industry '{pack_id}' missing 'path'")
        else:
            if path_value != expected_path:
                result.add(
                    f"{catalog_path}: industry '{pack_id}' should use path '{expected_path}', got '{path_value}'"
                )
            pack_dir = root / path_value
            if not pack_dir.is_dir():
                result.add(f"{catalog_path}: industry path not found: {path_value}")

        profiles = entry.get("profiles")
        if not isinstance(profiles, list):
            result.add(f"{catalog_path}: industry '{pack_id}' missing 'profiles' list")
        else:
            for profile_path in profiles:
                if not isinstance(profile_path, str) or not profile_path.strip():
                    result.add(
                        f"{catalog_path}: industry '{pack_id}' has invalid profile path '{profile_path}'"
                    )
                    continue
                if not (root / profile_path).is_file():
                    result.add(
                        f"{catalog_path}: industry '{pack_id}' profile not found: {profile_path}"
                    )

        industry_map[pack_id] = entry

    return industry_map


def load_profiles(root: Path, result: ValidationResult) -> dict[str, dict[str, Any]]:
    profiles_root = root / "profiles"
    if not profiles_root.exists():
        result.add(f"{profiles_root}: missing profiles directory")
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for profile_path in sorted(profiles_root.glob("*/*.yaml")):
        payload = load_yaml(profile_path, result)
        if not isinstance(payload, dict):
            result.add(f"{profile_path}: top-level YAML must be a mapping")
            continue

        profile_id = payload.get("name", profile_path.stem)
        if not isinstance(profile_id, str) or not profile_id.strip():
            result.add(f"{profile_path}: missing profile name")
            continue
        if profile_id in profiles:
            result.add(f"{profile_path}: duplicate profile id '{profile_id}'")
            continue

        models = payload.get("models")
        if not isinstance(models, list):
            result.add(f"{profile_path}: 'models' must be a list")

        services = payload.get("services")
        if not isinstance(services, list):
            result.add(f"{profile_path}: 'services' must be a list")

        profiles[profile_id] = {
            "id": profile_id,
            "pack_id": profile_path.parent.name,
            "path": profile_path.relative_to(root).as_posix(),
            "data": payload,
        }

    return profiles


def validate_model_catalog(
    root: Path,
    domain_map: dict[str, dict[str, Any]],
    industry_map: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> list[dict[str, Any]]:
    catalog_path = root / "library" / "catalog" / "models.yaml"
    if not catalog_path.exists():
        result.add(f"{catalog_path}: missing catalog file")
        return []

    data = _load_catalog_mapping(catalog_path, result)
    if data is None:
        return []

    models = data.get("models")
    if not isinstance(models, list):
        result.add(f"{catalog_path}: 'models' must be a list")
        return []

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    valid_models: list[dict[str, Any]] = []

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

        match = MODEL_PATH_RE.match(path_value)
        if not match:
            result.add(
                f"{catalog_path}: model entry '{entry_id}' path '{path_value}' must match "
                "library/domains/<domain_group>/<device_class>/<vendor>/<file>.yaml"
            )

        domain = entry.get("domain")
        if not isinstance(domain, str) or not domain.strip():
            result.add(f"{catalog_path}: model entry missing 'domain'")
        elif domain not in domain_map:
            result.add(
                f"{catalog_path}: model entry '{entry_id}' references unknown domain '{domain}'"
            )

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
                continue

            if list_key == "packages":
                for package_id in value:
                    if (
                        not isinstance(package_id, str)
                        or package_id not in industry_map
                    ):
                        result.add(
                            f"{catalog_path}: model entry '{entry_id}' references unknown package '{package_id}'"
                        )
            if list_key == "profiles":
                for profile_id in value:
                    if not isinstance(profile_id, str) or profile_id not in profiles:
                        result.add(
                            f"{catalog_path}: model entry '{entry_id}' references unknown profile '{profile_id}'"
                        )

        if (
            isinstance(domain, str)
            and isinstance(domain_group, str)
            and domain != domain_group
        ):
            result.add(
                f"{catalog_path}: model entry '{entry_id}' has domain '{domain}' "
                f"but domain_group '{domain_group}'"
            )

        if match:
            if isinstance(domain_group, str) and match.group("domain") != domain_group:
                result.add(
                    f"{catalog_path}: model entry '{entry_id}' path domain "
                    f"'{match.group('domain')}' does not match domain_group '{domain_group}'"
                )
            if (
                isinstance(device_class, str)
                and match.group("device_class") != device_class
            ):
                result.add(
                    f"{catalog_path}: model entry '{entry_id}' path device_class "
                    f"'{match.group('device_class')}' does not match device_class '{device_class}'"
                )
            if isinstance(vendor, str) and match.group("vendor") != vendor:
                result.add(
                    f"{catalog_path}: model entry '{entry_id}' path vendor "
                    f"'{match.group('vendor')}' does not match vendor '{vendor}'"
                )

        valid_models.append(entry)

    return valid_models


def validate_profiles(
    root: Path,
    profiles: dict[str, dict[str, Any]],
    model_paths: set[str],
    industry_map: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> None:
    for profile in profiles.values():
        profile_path = root / profile["path"]
        payload = profile["data"]
        pack_id = profile["pack_id"]

        if pack_id not in industry_map:
            result.add(f"{profile_path}: unknown pack directory '{pack_id}'")

        models = payload.get("models", [])
        if isinstance(models, list):
            for model_path in models:
                if not isinstance(model_path, str) or model_path not in model_paths:
                    result.add(
                        f"{profile_path}: references unknown model path '{model_path}'"
                    )


def _expected_pack_index_rows(
    models: list[dict[str, Any]], pack_id: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        packages = model.get("packages", [])
        if not isinstance(packages, list) or pack_id not in packages:
            continue
        rows.append({field: model.get(field, "") for field in PACK_INDEX_FIELDS})
    return sorted(rows, key=lambda row: (str(row["id"]), str(row["path"])))


def validate_pack_indexes(
    root: Path,
    models: list[dict[str, Any]],
    industry_map: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> None:
    industries_root = root / "library" / "industries"
    if not industries_root.exists():
        result.add(f"{industries_root}: missing industry directory")
        return

    for pack_id, industry in industry_map.items():
        path_value = industry.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            continue

        pack_dir = root / path_value
        if not pack_dir.is_dir():
            continue

        contents = {item.name for item in pack_dir.iterdir()}
        unsupported = contents - ALLOWED_PACK_FILES
        if unsupported:
            result.add(
                f"{pack_dir}: contains unsupported files/directories {sorted(unsupported)}"
            )

        yaml_files = sorted(item.name for item in pack_dir.glob("*.yaml"))
        if yaml_files != ["MODELS.yaml"]:
            result.add(
                f"{pack_dir}: expected only MODELS.yaml, found YAML files {yaml_files}"
            )

        pack_index_path = pack_dir / "MODELS.yaml"
        if not pack_index_path.exists():
            result.add(f"{pack_index_path}: missing pack model index")
            continue

        data = _load_catalog_mapping(pack_index_path, result)
        if data is None:
            continue
        index_models = data.get("models")
        if not isinstance(index_models, list):
            result.add(f"{pack_index_path}: 'models' must be a list")
            continue

        actual_rows = [
            {field: entry.get(field, "") for field in PACK_INDEX_FIELDS}
            for entry in index_models
            if isinstance(entry, dict)
        ]
        actual_rows = sorted(
            actual_rows, key=lambda row: (str(row["id"]), str(row["path"]))
        )
        expected_rows = _expected_pack_index_rows(models, pack_id)
        if actual_rows != expected_rows:
            result.add(
                f"{pack_index_path}: does not match models assigned to package '{pack_id}'"
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

    domain_map = validate_domains_catalog(root, result)
    industry_map = validate_industries_catalog(root, result)
    profiles = load_profiles(root, result)
    models = validate_model_catalog(root, domain_map, industry_map, profiles, result)
    model_paths = {
        model["path"]
        for model in models
        if isinstance(model.get("path"), str) and model.get("path")
    }
    validate_profiles(root, profiles, model_paths, industry_map, result)
    validate_pack_indexes(root, models, industry_map, result)
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
