"""Restore generated files before old containers reopen bind-mounted sources.

Copied into generated bundles; deliberately standard-library only.
"""

import json
from pathlib import Path
import shutil


def restore_files(journal_path: Path, *, mounts_only=False):
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    output = Path(journal["output"]).resolve()
    backup = Path(journal["backup"]).resolve()
    for entry in reversed(journal["files"]):
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid deployment journal entry")
        if mounts_only and relative.parts[0] not in {
            "library",
            "assets",
            "extensions",
            ".env",
            "startup-models.json",
        }:
            continue
        target = output / relative
        source = backup / relative
        if not target.resolve().is_relative_to(
            output
        ) or not source.resolve().is_relative_to(backup):
            raise ValueError("Deployment journal path escapes its directory")
        if entry["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            target.unlink(missing_ok=True)
    return journal.get("previous_api_url")
