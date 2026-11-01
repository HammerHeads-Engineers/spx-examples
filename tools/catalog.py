"""Public catalog authoring/distribution CLI. Run with python -m tools.catalog."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from tools.model_catalog import (
    CatalogError,
    ROOT,
    export_catalog,
    json_bytes,
    release_manifest,
    select_models,
    verify_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser(
        "build",
        help="Export metadata, selected resource files and deterministic offline archive",
    )
    build.add_argument("--version", required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--require-clean", action="store_true")
    verify = commands.add_parser(
        "verify", help="Verify schema, resources and archive hashes"
    )
    verify.add_argument("directory", type=Path)
    find = commands.add_parser(
        "list", help="Preview the installer's compatible-model selection"
    )
    find.add_argument("directory", type=Path)
    find.add_argument("--server", required=True)
    find.add_argument("--protocol", action="append", default=[])
    find.add_argument("--pack")
    find.add_argument("--include-deprecated", action="store_true")
    commands.add_parser("refresh", help="Regenerate pack indexes and README counts")
    new = commands.add_parser(
        "scaffold", help="Create a model draft, catalog entry and refreshed indexes"
    )
    new.add_argument("--id", required=True, dest="model_id")
    new.add_argument("--name", required=True)
    new.add_argument("--description", required=True)
    new.add_argument("--pack", action="append", default=[], dest="packs")
    new.add_argument(
        "--from",
        dest="copy_from",
        help="Existing model ID whose behavior and protocol bindings are copied",
    )
    new.add_argument("--domain-group")
    new.add_argument("--device-class")
    new.add_argument("--vendor")
    qualify = commands.add_parser(
        "qualify", help="Runtime qualification on a dedicated disposable server"
    )
    qualify.add_argument("directory", type=Path)
    target = qualify.add_mutually_exclusive_group(required=True)
    target.add_argument("--base-url")
    target.add_argument(
        "--target",
        help="Exact server version, resolved through SPX_CATALOG_QUALIFICATION_URLS JSON",
    )
    qualify.add_argument("--output", type=Path, required=True)
    qualify.add_argument("--allow-runtime-writes", action="store_true")
    qualify.add_argument(
        "--model",
        action="append",
        default=[],
        help="Diagnostic subset; cannot qualify a full stable catalog",
    )
    manifest = commands.add_parser(
        "release-manifest",
        help="Prepare publication metadata; stable enforces runtime evidence",
    )
    manifest.add_argument("directory", type=Path)
    manifest.add_argument("--channel", required=True, choices=["preview", "stable"])
    manifest.add_argument("--qualification", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.command == "build":
            document = export_catalog(
                root, args.output, args.version, require_clean=args.require_clean
            )
            result = {
                "status": "PASSED",
                "catalog": str(args.output / "catalog.json"),
                "models": len(document["models"]),
                "source": document["source"],
            }
        elif args.command == "verify":
            document = verify_catalog(args.directory)
            result = {
                "status": "PASSED",
                "models": len(document["models"]),
                "source": document["source"],
            }
        elif args.command == "list":
            result = select_models(
                verify_catalog(args.directory),
                args.server,
                protocols=args.protocol,
                pack=args.pack,
                include_deprecated=args.include_deprecated,
            )
        elif args.command == "refresh":
            from tools.scaffold_model import refresh

            refresh(root)
            result = {
                "status": "PASSED",
                "message": "Pack indexes and README refreshed; review the diff",
            }
        elif args.command == "scaffold":
            from tools.scaffold_model import scaffold

            fields = (
                "model_id",
                "name",
                "description",
                "packs",
                "copy_from",
                "domain_group",
                "device_class",
                "vendor",
            )
            path = scaffold(root, **{field: getattr(args, field) for field in fields})
            result = {
                "status": "DRAFT",
                "model": str(path),
                "next": "Review behavior and bindings, add meaningful tests, then run python -m tools.check",
            }
        elif args.command == "qualify":
            from tools.qualify_catalog import qualify_catalog

            base_url = args.base_url
            if args.target:
                urls = json.loads(
                    os.environ.get("SPX_CATALOG_QUALIFICATION_URLS", "{}")
                )
                if args.target not in urls:
                    raise CatalogError(
                        f"Configure SPX_CATALOG_QUALIFICATION_URLS for target {args.target}"
                    )
                base_url = urls[args.target]
            result = qualify_catalog(
                args.directory,
                base_url,
                allow_writes=args.allow_runtime_writes,
                model_ids=args.model,
                expected_server=args.target,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(json_bytes(result))
            print(json.dumps(result, indent=2))
            return int(result["status"] != "PASSED")
        else:
            result = release_manifest(args.directory, args.channel, args.qualification)
            for path, qualified in zip(args.qualification, result["qualification"]):
                destination = args.directory / qualified["file"]
                if path.resolve() != destination.resolve():
                    shutil.copyfile(path, destination)
            (args.directory / "release.json").write_bytes(json_bytes(result))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (CatalogError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
