"""The same public, credential-free contribution checks locally and in CI.

Run ``poetry run python -m tools.check``. Use --json for agent consumption;
--no-tests is a fast structural check and is not sufficient for publication.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.model_catalog import CatalogError, ROOT, export_catalog
from tools.validate_models import validate_models


def check(root: Path, *, tests=True, base_ref=None) -> dict:
    checks = []

    def record(name, issues):
        checks.append(
            {"name": name, "status": "FAILED" if issues else "PASSED", "issues": issues}
        )

    result = validate_models(root)
    record("models-and-pack-indexes", result.errors)
    if base_ref:
        from tools.catalog_compatibility import public_contract_issues

        try:
            record("public-model-compatibility", public_contract_issues(root, base_ref))
        except (CatalogError, OSError, ValueError, TypeError, KeyError) as exc:
            record("public-model-compatibility", [str(exc)])
    try:
        with tempfile.TemporaryDirectory(prefix="spx-catalog-check-") as directory:
            for channel in ("preview", "stable"):
                export_catalog(
                    root, Path(directory) / channel, "local-check", channel=channel
                )
        record("distribution-contract-and-artifacts", [])
    except (CatalogError, OSError, ValueError, TypeError, KeyError) as exc:
        record("distribution-contract-and-artifacts", [str(exc)])
    commands = [
        (
            "readme-catalog",
            [sys.executable, "scripts/render_readme_catalog.py", "--check"],
        )
    ]
    if tests:
        commands.append(
            (
                "unit-tests",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/core/unit",
                    "tests/mcp/unit",
                    "tests/catalog",
                    *[
                        str(path.relative_to(root))
                        for path in sorted((root / "tests/packs").glob("*/unit"))
                    ],
                ],
            )
        )
    for name, command in commands:
        process = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        record(name, [process.stdout + process.stderr] if process.returncode else [])
        checks[-1]["summary"] = next(
            (
                line
                for line in reversed((process.stdout + process.stderr).splitlines())
                if line.strip()
            ),
            "",
        )
    return {
        "schema_version": 1,
        "status": (
            "FAILED" if any(c["status"] == "FAILED" for c in checks) else "PASSED"
        ),
        "scope": "full" if tests else "structural",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--json", action="store_true", help="Emit one machine-readable JSON document"
    )
    parser.add_argument(
        "--no-tests", action="store_true", help="Fast structural iteration only"
    )
    parser.add_argument("--report", type=Path, help="Also save the JSON report")
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("SPX_CATALOG_BASE_REF") or None,
        help="Compare public interfaces and declared server targets with this Git revision",
    )
    args = parser.parse_args()
    report = check(args.root.resolve(), tests=not args.no_tests, base_ref=args.base_ref)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for item in report["checks"]:
            print(f"{item['status']}: {item['name']}")
            if item.get("summary") and not item["issues"]:
                print(item["summary"])
            for issue in item["issues"]:
                print(issue)
        print(f"Contribution checks: {report['status']} ({report['scope']})")
    return int(report["status"] != "PASSED")


if __name__ == "__main__":
    raise SystemExit(main())
