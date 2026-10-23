# SPDX-License-Identifier: MIT
"""Reject unremediated shipped Python images without patching them during QA."""

import argparse
import json
import subprocess

from installer.compatibility import SPX_SERVER_VERSION
from installer.manifest import ManifestLoader
from installer.runtime_bootstrap import SECURITY_MINIMUMS, safe_version


PROBE = """
import json, ssl, sys
from importlib.metadata import distributions
versions = {d.metadata['Name'].lower(): d.version for d in distributions()
            if d.metadata.get('Name', '').lower() in ('pip', 'certifi', 'uv')}
context = ssl.create_default_context()
if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
    raise RuntimeError('Default TLS verification is disabled')
if any('emSign ECC Root CA - G3' in str(cert['subject']) for cert in context.get_ca_certs()):
    raise RuntimeError('System trust retains compromised emSign G3 root')
print(json.dumps(dict(versions, python=sys.version.split()[0], executable=sys.executable)))
"""


def shipped_images():
    images = {f"simplephysx/spx-server:{SPX_SERVER_VERSION}"}
    for service in ManifestLoader().load().services.values():
        image = service.deployment.image if service.deployment else None
        if image and ("home-assistant" in image or "python-matter-server" in image):
            images.add(image)
    return sorted(images)


def validate_versions(versions):
    for name, minimum in SECURITY_MINIMUMS.items():
        if name in versions and not safe_version(versions[name], minimum):
            raise RuntimeError(
                f"Unsafe image package {name}={versions[name]}; require >= {minimum}"
            )


def verify_image(image, *, pull=True):
    if pull:
        subprocess.run(["docker", "pull", image], check=True)
    results = []
    # SPX and the catalog's Python providers ship application and base interpreters.
    for python in ("python", "/usr/local/bin/python"):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                python,
                image,
                "-c",
                PROBE,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                f"Image security probe failed for {image} ({python}): {result.stderr.strip()}"
            )
        versions = json.loads(result.stdout)
        validate_versions(versions)
        results.append(versions)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        action="append",
        help="Override catalog images for local qualification.",
    )
    parser.add_argument(
        "--no-pull", action="store_true", help="Inspect a locally built image."
    )
    args = parser.parse_args()
    report = {
        image: verify_image(image, pull=not args.no_pull)
        for image in (args.image or shipped_images())
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
