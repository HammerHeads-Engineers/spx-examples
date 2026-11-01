"""Compare public model contracts with a PR base without executing model code."""

from pathlib import Path
import subprocess

import yaml

from tools.model_catalog import CatalogError, git, read_yaml, server_matches


def public_contract_issues(root: Path, base_ref: str) -> list[str]:
    commit = git(
        root, "rev-parse", "--verify", "--end-of-options", base_ref + "^{commit}"
    )

    def previous(path, optional=False):
        result = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True
        )
        if result.returncode:
            if optional:
                return {}
            raise CatalogError(f"{path}: cannot read model contract at {base_ref}")
        return yaml.safe_load(result.stdout)

    older = previous("library/catalog/models.yaml")["models"]
    current = {
        entry["id"]: entry
        for entry in read_yaml(root / "library/catalog/models.yaml")["models"]
    }
    old_config = previous("library/catalog/distribution.yaml", optional=True)
    new_config = read_yaml(root / "library/catalog/distribution.yaml")
    issues = []
    for old in older:
        label = f"{old['path']} ({old['id']})"
        new = current.get(old["id"])
        if new is None:
            issues.append(
                f"{label}: model ID removed; retain and deprecate it in the maintained line"
            )
            continue
        if new["path"] != old["path"]:
            issues.append(
                f"{label}: published model path changed; preserve it for existing consumers"
            )
        old_definition = previous(old["path"])
        new_definition = read_yaml(root / new["path"])
        for section in ("attributes", "meta_parameters", "scenarios"):
            old_names = {
                key
                for key in old_definition.get(section, {})
                if not key.startswith("_")
            }
            removed = old_names - set(new_definition.get(section, {}))
            if removed:
                issues.append(
                    f"{label}: public {section} removed: {sorted(removed)}; retain the interface or add a new model variant"
                )
        if old_config:
            old_spec = old.get("distribution", {}).get(
                "server_compatibility", old_config["server_compatibility"]
            )
            new_spec = new.get("distribution", {}).get(
                "server_compatibility", new_config["server_compatibility"]
            )
            for target in old_config["qualification_targets"]:
                if server_matches(old_spec, target) and not server_matches(
                    new_spec, target
                ):
                    issues.append(
                        f"{label}: compatibility with previous target {target} was removed"
                    )
    return issues
