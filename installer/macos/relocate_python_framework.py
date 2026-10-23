"""Relocate the verified Python payload without touching a host installation."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

VENDOR_ROOT = "/Library/Frameworks/Python.framework"
MACHO_MAGICS = {
    bytes.fromhex(value)
    for value in (
        "cafebabe",
        "bebafeca",
        "cafebabf",
        "bfbafeca",
        "cffaedfe",
        "cefaedfe",
        "feedfacf",
        "feedface",
    )
}


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)


def relocate(
    framework: Path, destination: str, identity: str = "-", keychain: str = ""
) -> None:
    signing = [
        "codesign",
        "--force",
        "--sign",
        identity,
        "--preserve-metadata=entitlements",
    ]
    if identity != "-":
        signing += ["--timestamp", "--options", "runtime"]
    if keychain:
        signing += ["--keychain", keychain]

    def sign(path: Path) -> None:
        subprocess.run([*signing, str(path)], check=True)

    changed = 0
    for path in sorted(framework.rglob("*")):
        if path.is_symlink() or not path.is_file() or "_CodeSignature" in path.parts:
            continue
        data = path.read_bytes()
        if data[:4] in MACHO_MAGICS:
            ids = output("otool", "-D", str(path)).splitlines()
            library_id = next(
                (line for line in ids if line.startswith(VENDOR_ROOT + "/")), None
            )
            dependencies = {
                line.strip().split(" (compatibility", 1)[0]
                for line in output("otool", "-L", str(path)).splitlines()
                if line.strip().startswith(VENDOR_ROOT + "/")
            }
            arguments = []
            for dependency in sorted(dependencies - {library_id}):
                arguments += [
                    "-change",
                    dependency,
                    dependency.replace(VENDOR_ROOT, destination, 1),
                ]
            if library_id:
                arguments += ["-id", library_id.replace(VENDOR_ROOT, destination, 1)]
            rpath = False
            rpaths = set()
            for line in output("otool", "-l", str(path)).splitlines():
                text = line.strip()
                if text.startswith("cmd "):
                    rpath = text == "cmd LC_RPATH"
                elif rpath and text.startswith("path " + VENDOR_ROOT):
                    old = text[5:].split(" (offset", 1)[0]
                    rpaths.add(old)
            for old in sorted(rpaths):
                arguments += ["-rpath", old, old.replace(VENDOR_ROOT, destination, 1)]
            if arguments:
                subprocess.run(["install_name_tool", *arguments, str(path)], check=True)
                sign(path)
                changed += 1
        elif b"\0" not in data:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if VENDOR_ROOT not in text:
                continue
            # Tcl/Tk configuration scripts can have signatures in xattrs.
            signed = (
                subprocess.run(
                    ["codesign", "--display", str(path)], capture_output=True
                ).returncode
                == 0
            )
            path.write_text(text.replace(VENDOR_ROOT, destination), encoding="utf-8")
            if signed:
                sign(path)

    # Rebuild nested seals inside-out. The caller signs the enclosing Python
    # framework after it has also generated all standard-library bytecode.
    bundles = [
        p
        for p in framework.rglob("*")
        if not p.is_symlink() and p.is_dir() and p.suffix in (".framework", ".app")
    ]
    for bundle in sorted(bundles, key=lambda p: len(p.parts), reverse=True):
        sign(bundle)
    print(f"Relocated {changed} Mach-O objects to {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework", type=Path)
    parser.add_argument("destination")
    parser.add_argument("--identity", default="-")
    parser.add_argument("--keychain", default="")
    args = parser.parse_args()
    relocate(args.framework, args.destination, args.identity, args.keychain)
