"""Exercise native framework signatures through the actual Python packager."""

import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or sys.version_info[:2] != (3, 13),
    reason="Requires macOS signing tools and the bundled Python 3.13 bytecode compiler",
)


def run(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def framework(path, version, library):
    name = path.stem
    current = path / "Versions" / version
    resources = current / "Resources"
    resources.mkdir(parents=True)
    (path / "Versions" / "Current").symlink_to(version)
    (path / name).symlink_to(f"Versions/Current/{name}")
    (path / "Resources").symlink_to("Versions/Current/Resources")
    (resources / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": f"com.example.spx.signature-fixture.{name.lower()}",
                "CFBundleExecutable": name,
                "CFBundlePackageType": "FMWK",
                "CFBundleVersion": "1.0",
            }
        )
    )
    shutil.copy2(library, current / name)
    return current


def test_nested_signatures_survive_python_component_repackaging(tmp_path):
    source = tmp_path / "fixture.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    library, executable = tmp_path / "fixture.dylib", tmp_path / "fixture"
    run(
        "clang",
        "-arch",
        "arm64",
        "-arch",
        "x86_64",
        "-dynamiclib",
        "-install_name",
        "/Library/Frameworks/Python.framework/Versions/3.13/Python",
        str(source),
        "-o",
        str(library),
    )
    run(
        "clang",
        "-arch",
        "arm64",
        "-arch",
        "x86_64",
        str(source),
        "-Wl,-rpath,/Library/Frameworks/Python.framework/Versions/3.13",
        "-o",
        str(executable),
    )

    python = tmp_path / "source" / "Python.framework"
    version = framework(python, "3.13", library)
    for name in ("Tcl", "Tk"):
        nested = version / "Frameworks" / f"{name}.framework"
        nested_version = framework(nested, "8.6", library)
        script = nested_version / f"{name.lower()}Config.sh"
        script.write_text(
            "#!/bin/sh\nprefix=/Library/Frameworks/Python.framework\nexit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        run("codesign", "--force", "--sign", "-", str(script))
        # These non-Mach-O signatures are exactly what rsync -a used to drop.
        assert "com.apple.cs.CodeDirectory" in run("xattr", str(script)).stdout

        run("codesign", "--force", "--sign", "-", str(nested))

    bin_dir = version / "bin"
    bin_dir.mkdir()
    shutil.copy2(executable, bin_dir / "python3.13")
    run("codesign", "--force", "--sign", "-", str(bin_dir / "python3.13"))
    app = version / "Resources" / "Python.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    shutil.copy2(executable, app / "Contents" / "MacOS" / "Python")
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "com.example.spx.signature-fixture.launcher",
                "CFBundleExecutable": "Python",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1.0",
            }
        )
    )
    run("codesign", "--force", "--sign", "-", str(app))
    object_file = version / "lib" / "python3.13" / "config-3.13-darwin" / "python.o"
    object_file.parent.mkdir(parents=True)
    object_file.write_bytes(b"development-only object\n")
    module = version / "lib" / "python3.13" / "signature_probe.py"
    module.write_text(
        '"""A runtime import must not change the framework seal."""\nvalue = 42\n'
    )
    run("codesign", "--force", "--sign", "-", str(python))
    run("codesign", "--verify", "--deep", "--strict", str(python))

    component = tmp_path / "Python_Framework.pkg"
    package = tmp_path / "python-source.pkg"
    run(
        "pkgbuild",
        "--root",
        str(python),
        "--identifier",
        "com.example.spx.python-fixture",
        "--version",
        "3.13.17",
        "--install-location",
        "/Library/Frameworks/Python.framework",
        str(component),
    )
    run("productbuild", "--package", str(component), str(package))

    staging = tmp_path / "staging"
    staging.mkdir()
    # Load the builder's real functions without executing its CLI/app build.
    script = (ROOT / "scripts/build_macos_pkg.sh").read_text(encoding="utf-8")
    harness = tmp_path / "prepare.sh"
    harness.write_text(
        script.split('\nOUTPUT_DIR="dist"', 1)[0] + "\nprepare_python_component\n",
        encoding="utf-8",
    )
    output = staging / "python-component.pkg"
    env = {
        **os.environ,
        "STAGING_ROOT": str(staging),
        "REPO_ROOT": str(ROOT),
        "PYTHON_VERSION": "3.13.17",
        "PYTHON_FRAMEWORK_VERSION": "3.13",
        "PYTHON_FRAMEWORK_ROOT": str(staging / "Python.framework"),
        "PYTHON_PACKAGE_INPUT": str(package),
        "PYTHON_PACKAGE_SHA256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "APP_SIGN_IDENTITY": "",
        "SIGN_IDENTITY": "",
        "KEYCHAIN_PATH": "",
        "INSTALL_LOCATION": "/Applications",
        "TOOLS_DIR_NAME": "SPX Tools",
        "PYTHON_COMPONENT_ID": "com.example.spx.repacked-python",
        "PYTHON_COMPONENT_PKG_PATH": str(output),
        "SPX_BUILD_PYTHON": sys.executable,
    }
    run("bash", str(harness), env=env)

    payload = staging / "python-component-inspection" / "Payload" / "Versions" / "3.13"
    assert output.is_file()
    assert not list(payload.rglob("*.o"))
    run("codesign", "--verify", "--deep", "--strict", str(payload / "Python"))
    caches = list(
        (payload / "lib/python3.13/__pycache__").glob("signature_probe.*.pyc")
    )
    assert len(caches) == 3
    before = {path.relative_to(payload): path.read_bytes() for path in caches}
    # Import the packaged module at all supported optimization levels. Use a
    # real matching interpreter; the Mach-O fixture above is intentionally tiny.
    for flags in ([], ["-O"], ["-OO"]):
        run(
            sys.executable,
            *flags,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import signature_probe; assert signature_probe.value == 42",
            str(payload / "lib/python3.13"),
        )
    after = list((payload / "lib/python3.13/__pycache__").glob("signature_probe.*.pyc"))
    assert before == {path.relative_to(payload): path.read_bytes() for path in after}
    postinstall = (staging / "python-scripts/postinstall").read_text()
    assert (
        "/Library/SPX/Python.framework"
        in run("otool", "-D", str(payload / "Python")).stdout
    )
    assert (
        "/Library/Frameworks/Python.framework"
        not in run("otool", "-l", str(payload / "bin/python3.13")).stdout
    )
    assert "compileall" not in postinstall
    run("bash", str(staging / "python-scripts/postinstall"), env={**env, "CI": "1"})
    run("codesign", "--verify", "--deep", "--strict", str(payload / "Python"))
    for name in ("Tcl", "Tk"):
        nested = payload / "Frameworks" / f"{name}.framework"
        run("codesign", "--verify", "--deep", "--strict", str(nested))
        script = nested / "Versions" / "8.6" / f"{name.lower()}Config.sh"
        assert "com.apple.cs.CodeDirectory" in run("xattr", str(script)).stdout
        assert "prefix=/Library/SPX/Python.framework" in script.read_text()
