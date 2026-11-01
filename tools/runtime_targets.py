"""Freeze the public stable/RC server images and declared qualification targets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests
from semantic_version import Version

from tools.model_catalog import CatalogError, ROOT, json_bytes, verify_catalog

PINNED_IMAGE = re.compile(
    r"[a-z0-9][a-z0-9./_-]*(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}\Z"
)


def fixture_config() -> dict:
    value = json.loads((ROOT / "tests/runtime/images.json").read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or set(value["services"]) != {
        "mqtt",
        "knx",
        "lwm2m",
        "matter",
    }:
        raise CatalogError("Invalid CI fixture image configuration")
    if not all(PINNED_IMAGE.fullmatch(image) for image in value["services"].values()):
        raise CatalogError("CI dependency images must be pinned by SHA-256 digest")
    return value


def plan_targets(tags: list[dict], declared: list[str], repository: str) -> dict:
    versions = {}
    for tag in tags:
        name = tag.get("name", "")
        try:
            version = Version(name.removeprefix("v"))
        except ValueError:
            continue
        if version.build or (
            version.prerelease
            and not re.fullmatch(r"rc\.\d+", ".".join(version.prerelease))
        ):
            continue
        digest = tag.get("digest", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise CatalogError(
                f"{name}: registry did not provide an immutable manifest digest"
            )
        versions[version] = (name, digest)
    stable = [v for v in versions if not v.prerelease]
    rc = [v for v in versions if v.prerelease]
    if not stable or not rc:
        raise CatalogError(
            "The runtime matrix requires a published stable and RC image"
        )
    declared_versions = {Version(value.removeprefix("v")) for value in declared}
    requested = {max(stable): "stable", max(rc): "rc"}
    for version in declared_versions:
        requested.setdefault(version, "declared")
    rows = []
    for version, channel in requested.items():
        if version not in versions:
            raise CatalogError(
                f"Declared server target {version} has no published image"
            )
        tag, digest = versions[version]
        rows.append(
            {
                "channel": channel,
                "version": str(version),
                "image": f"{repository}:{tag}@{digest}",
                "qualifying": version in declared_versions,
            }
        )
    return {"include": rows}


def resolve_targets(directory: Path) -> dict:
    document = verify_catalog(directory)
    repository = fixture_config()["server_repository"]
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags?page_size=100"
    prefix = f"https://hub.docker.com/v2/repositories/{repository}/tags"
    tags = []
    for _ in range(30):
        if not url:
            break
        if not url.startswith(prefix):
            raise CatalogError("Unexpected registry pagination URL")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        value = response.json()
        tags.extend(value["results"])
        url = value.get("next")
    else:
        raise CatalogError("Too many registry pages; narrow or update the resolver")
    return plan_targets(tags, document["qualification_targets"], repository)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    value = resolve_targets(args.catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json_bytes(value))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write("matrix=" + json.dumps(value, separators=(",", ":")) + "\n")
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
