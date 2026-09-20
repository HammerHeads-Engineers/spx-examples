# macOS installer release gate

The signed `.pkg` is a release/manual gate, separate from unit tests. Run this
check on a clean macOS host with Docker Desktop and a staging Community key.

1. Build with `scripts/build_macos_pkg.sh`, an Apple Developer ID Application
   identity, a Developer ID Installer identity, and notarization credentials.
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

The same checklist applies to the portable `.tgz` and `.run` flows where their
platform supports them; only the native `.pkg` adds Apple signing and
notarization checks.
