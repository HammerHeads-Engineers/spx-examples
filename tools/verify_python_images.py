# SPDX-License-Identifier: MIT
"""Reject unremediated shipped Python images without patching them during QA."""

import argparse
import json
from pathlib import Path
import subprocess

import yaml

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

PYTHON_IMAGE_REPOSITORIES = (
    "simplephysx/spx-server",
    "ghcr.io/home-assistant/home-assistant",
    "ghcr.io/home-assistant-libs/python-matter-server",
)


def is_python_image(image):
    return any(
        image == repository
        or image.startswith(repository + ":")
        or image.startswith(repository + "@")
        for repository in PYTHON_IMAGE_REPOSITORIES
    )


def compose_python_images(path):
    """Qualify Python providers selected for this bundle, including optional ones."""
    compose = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    images = {
        service["image"]
        for service in compose["services"].values()
        if service.get("image") and is_python_image(service["image"])
    }
    if not any(
        image == PYTHON_IMAGE_REPOSITORIES[0]
        or image.startswith(PYTHON_IMAGE_REPOSITORIES[0] + ":")
        or image.startswith(PYTHON_IMAGE_REPOSITORIES[0] + "@")
        for image in images
    ):
        raise ValueError("Generated Compose must include the SPX Server image")
    return sorted(images)


def shipped_images():
    images = {f"simplephysx/spx-server:{SPX_SERVER_VERSION}"}
    for service in ManifestLoader().load().services.values():
        image = service.deployment.image if service.deployment else None
        if image and is_python_image(image):
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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--image",
        action="append",
        help="Override catalog images for local qualification.",
    )
    selection.add_argument(
        "--compose", type=Path, help="Verify the Python images in a generated stack."
    )
    parser.add_argument(
        "--no-pull", action="store_true", help="Inspect a locally built image."
    )
    args = parser.parse_args()
    selected = (
        compose_python_images(args.compose)
        if args.compose
        else args.image or shipped_images()
    )
    report = {
        image: verify_image(image, pull=not args.no_pull)
        for image in selected
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
