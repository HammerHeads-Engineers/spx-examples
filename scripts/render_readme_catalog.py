#!/usr/bin/env python3
"""Keep the README overview in sync with the local public catalogs."""
from collections import Counter
from pathlib import Path
import argparse
import yaml

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- catalog-overview:start -->"
END = "<!-- catalog-overview:end -->"


def render(root=ROOT):
    models = yaml.safe_load(
        (root / "library/catalog/models.yaml").read_text(encoding="utf-8")
    )["models"]
    packs = yaml.safe_load(
        (root / "library/catalog/industries.yaml").read_text(encoding="utf-8")
    )["industries"]
    domains = Counter(m.get("domain_group", m.get("domain")) for m in models)
    protocols = sorted({v for m in models for v in m.get("protocols", [])})
    eligible = Counter(
        channel
        for model in models
        for channel in model.get("distribution", {}).get(
            "channels", ["preview", "stable"]
        )
    )
    lines = [
        START,
        "",
        f"Source library: **{len(models)} models** across {len(domains)} domain groups.",
        "",
        f"Channel eligibility in this checkout: **{eligible['preview']} preview / {eligible['stable']} stable**.",
        "These counts describe source policy; released contents and qualification are recorded in release assets.",
        "",
        "| Domain group | Models |",
        "| --- | ---: |",
    ]
    lines += [f"| `{d}` | {n} |" for d, n in sorted(domains.items())]
    lines += [
        "",
        "Packs: "
        + ", ".join(
            f'[`{p["id"]}`](library/industries/{p["id"]}/README.md)' for p in packs
        )
        + ".",
        "",
        "Protocol tags: " + ", ".join(f"`{p}`" for p in protocols) + ".",
        "",
        "These are reference simulations, not manufacturer-certified digital twins.",
        END,
    ]
    return "\n".join(lines)


def refresh(root=ROOT, *, check=False):
    readme = root / "README.md"
    current = readme.read_text(encoding="utf-8")
    if current.count(START) != 1 or current.count(END) != 1:
        raise ValueError("README must contain exactly one overview block")
    a = current.index(START)
    b = current.index(END) + len(END)
    expected = current[:a] + render(root) + current[b:]
    if check:
        if expected != current:
            raise SystemExit("README catalog overview is stale")
        print("README catalog overview is current.")
    else:
        readme.write_text(expected, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    refresh(check=args.check)


if __name__ == "__main__":
    main()
