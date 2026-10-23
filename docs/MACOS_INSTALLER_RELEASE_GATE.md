# macOS installer release gate

The signed `.pkg` is a release/manual gate, separate from unit tests. Run this
check on a clean macOS host with Docker Desktop and a staging Community key.

1. Build with `scripts/build_macos_pkg.sh`, an Apple Developer ID Application
   identity, a Developer ID Installer identity, and notarization credentials.
   The build interpreter must match bundled Python 3.13; set `SPX_BUILD_PYTHON`
   when it is not the `python3` on PATH. Bytecode for normal, `-O`, and `-OO`
   execution is generated before signing with checked source hashes and the
   final installation paths. Postinstall must not modify the framework.
2. Verify the SHA-256 checksum, `pkgutil --check-signature`,
   `xcrun stapler validate`, and `spctl -a -vv -t install`.
3. Install the package, open **SPX Setup.app**, choose Industrial Pack →
   `process_cell_quickstart`, and confirm the summary shows no more than five
   automatic starts. The profile is additive to the selected pack.
4. Confirm API `8000`, UI `3000`, healthcheck, license acceptance, model
   registration, instance creation, and start/stop operations.
5. Run Setup a second time. The preflight must show project `spx`, images,
   configuration path, labels and occupied ports, then ask for confirmation.
   Declining must finish before `compose up`.
6. Force a bootstrap failure. The output must identify the bootstrap/model or
   instance stage, omit the Product Key, stop only the current transaction, and
   restore the previous stack. Unrelated containers, images and volumes must
   remain unchanged.
7. After installation, Setup, and MCP bootstrap, import standard-library
   modules at all three optimization levels and verify the installed seal:

   ```bash
   framework=/Library/Frameworks/Python.framework
   for optimization in 0 1 2; do
     PYTHONOPTIMIZE="$optimization" "$framework/Versions/3.13/bin/python3.13" -I -c \
       'import asyncio, compileall, ensurepip, ssl, tkinter, venv'
   done
   codesign --verify --deep --strict --verbose=2 "$framework"
   ```

   Verification of the extracted package alone cannot detect postinstall or
   runtime cache writes. The native ARM64 and Intel smoke jobs require this
   check after using the installed runtime.

The same checklist applies to the portable `.tgz` and `.run` flows where their
platform supports them; only the native `.pkg` adds Apple signing and
notarization checks.
