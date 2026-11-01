"""Check runtime evidence without turning advisory compatibility probes into claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.model_catalog import (
    digest,
    json_bytes,
    select_models,
    verify_catalog,
)
from tools.runtime_targets import fixture_config


def check_reports(catalog: Path, matrix: dict, directory: Path) -> dict:
    document = verify_catalog(catalog)
    catalog_hash = digest((catalog / "catalog.json").read_bytes())
    rows = []
    required_count = 0
    for target in matrix["include"]:
        required = target["qualifying"]
        filename = (
            f"qualification-{target['version']}.json"
            if required
            else f"probe-{target['channel']}-{target['version']}.json"
        )
        path = directory / filename
        report = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        models = (
            select_models(document, target["version"], include_deprecated=True)
            if required
            else document["models"]
        )
        deferred = set(fixture_config()["deferred_protocols"])
        excluded = {m["id"] for m in models if set(m["protocols"]) & deferred}
        expected = {m["id"] for m in models} - excluded
        results = report.get("results", [])
        expected_scope = (
            ("diagnostic-subset" if excluded else "full-catalog")
            if required
            else "compatibility-probe"
        )
        valid = bool(expected) and (
            report.get("schema_version") == 1
            and report.get("status") == "PASSED"
            and report.get("source_commit") == document["source"]["commit"]
            and report.get("catalog_sha256") == catalog_hash
            and report.get("server_version") == target["version"]
            and report.get("environment", {}).get("server_image") == target["image"]
            and report.get("scope") == expected_scope
            and set(report.get("excluded_models", [])) == excluded
            and len(results) == len(expected)
            and {row.get("model_id") for row in results} == expected
            and all(
                all(
                    row.get(field) == "PASSED"
                    for field in (
                        "registration",
                        "startup",
                        "behavior",
                        "lifecycle",
                        "cleanup",
                    )
                )
                for row in results
            )
        )
        if required:
            required_count += 1
        rows.append(
            {
                "channel": target["channel"],
                "server": target["version"],
                "required": required,
                "status": "PASSED" if valid else "FAILED",
                "tested": len(results),
                "excluded": sorted(excluded),
                "report": filename,
            }
        )
    return {
        "schema_version": 1,
        "status": (
            "PASSED"
            if required_count
            and all(row["status"] == "PASSED" for row in rows if row["required"])
            else "FAILED"
        ),
        "source_commit": document["source"]["commit"],
        "catalog_sha256": catalog_hash,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("reports", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    result = check_reports(
        args.catalog, json.loads(args.matrix.read_text(encoding="utf-8")), args.reports
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json_bytes(result))
    if args.summary:
        lines = [
            "## Model runtime compatibility",
            "",
            "| Channel | SPX Server | Policy | Result | Models tested |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in result["rows"]:
            lines.append(
                f"| {row['channel']} | {row['server']} | {'Required declared target' if row['required'] else 'Advisory compatibility probe'} | {row['status']} | {row['tested']} |"
            )
        lines += [
            "",
            "BLE is deferred to a later model release. Stable candidates omit its two models; preview software tests record them as excluded, never as passed.",
            "",
            "Advisory probes do not change the catalog's declared server compatibility.",
            "",
        ]
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    print(json.dumps(result, indent=2))
    return int(result["status"] != "PASSED")


if __name__ == "__main__":
    raise SystemExit(main())
