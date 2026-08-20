#!/usr/bin/env python3
"""Create and fail-closed validate WMS offline release manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$")
EXPECTED_SERVICES = {
    "api": "backend",
    "migrations": "backend",
    "celery_worker": "backend",
    "celery_beat": "backend",
    "web": "web",
}


def fail(message: str) -> None:
    raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_artifact(name: str, value: Any, artifact_dir: Path) -> dict[str, str]:
    if not isinstance(value, dict):
        fail(f"artifact {name} must be an object")
    required = ("file", "sha256", "image", "image_id")
    if set(value) != set(required):
        fail(f"artifact {name} must contain only: {', '.join(required)}")

    archive_name = value["file"]
    if not isinstance(archive_name, str) or Path(archive_name).name != archive_name or not archive_name.endswith(".tar.gz"):
        fail(f"artifact {name} file must be a safe .tar.gz basename")
    for field in ("sha256", "image_id"):
        if not isinstance(value[field], str) or not DIGEST_RE.fullmatch(value[field]):
            fail(f"artifact {name} {field} must be a sha256 digest")
    if not isinstance(value["image"], str) or not IMAGE_RE.fullmatch(value["image"]):
        fail(f"artifact {name} image is not a supported Docker image reference")

    archive = artifact_dir / archive_name
    if not archive.is_file():
        fail(f"artifact {name} archive is missing: {archive}")
    actual = sha256_file(archive)
    if actual != value["sha256"]:
        fail(f"artifact {name} archive digest mismatch: expected {value['sha256']}, got {actual}")
    return {field: value[field] for field in required}


def validate_manifest(manifest_path: Path, release_sha: str, artifact_dir: Path) -> dict[str, dict[str, str]]:
    if not SHA_RE.fullmatch(release_sha):
        fail("release SHA must be a lowercase 40-character Git SHA")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read release manifest: {error}")
    if not isinstance(manifest, dict):
        fail("release manifest must be a JSON object")
    if manifest.get("schema_version") != "wms.release-manifest/v1":
        fail("unsupported release manifest schema_version")
    if manifest.get("delivery") != "offline":
        fail("only explicit offline manifests are accepted by this deployment path")
    if manifest.get("release_sha") != release_sha:
        fail(f"release manifest SHA mismatch: expected {release_sha}, got {manifest.get('release_sha')!r}")
    if manifest.get("services") != EXPECTED_SERVICES:
        fail("release manifest service mapping is incomplete or changed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"backend", "web"}:
        fail("release manifest must contain backend and web artifacts only")
    return {name: validate_artifact(name, artifacts[name], artifact_dir) for name in ("backend", "web")}


def command_create(args: argparse.Namespace) -> int:
    release_sha = args.release_sha
    if not SHA_RE.fullmatch(release_sha):
        fail("release SHA must be a lowercase 40-character Git SHA")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, str]] = {}
    for name, archive_arg, image, image_id in (
        ("backend", args.backend_archive, args.backend_image, args.backend_image_id),
        ("web", args.web_archive, args.web_image, args.web_image_id),
    ):
        archive = Path(archive_arg).resolve()
        if archive.parent != output or not archive.is_file():
            fail(f"{name} archive must be an existing file directly inside {output}")
        if not IMAGE_RE.fullmatch(image):
            fail(f"{name} image is not a supported Docker image reference")
        if not DIGEST_RE.fullmatch(image_id):
            fail(f"{name} image ID must be a sha256 digest")
        artifacts[name] = {
            "file": archive.name,
            "sha256": sha256_file(archive),
            "image": image,
            "image_id": image_id,
        }
    manifest = {
        "schema_version": "wms.release-manifest/v1",
        "delivery": "offline",
        "release_sha": release_sha,
        "artifacts": artifacts,
        "services": EXPECTED_SERVICES,
    }
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


def command_validate(args: argparse.Namespace) -> int:
    validate_manifest(Path(args.manifest), args.release_sha, Path(args.artifact_dir))
    print("release manifest is valid")
    return 0


def command_metadata(args: argparse.Namespace) -> int:
    artifacts = validate_manifest(Path(args.manifest), args.release_sha, Path(args.artifact_dir))
    for name in ("backend", "web"):
        artifact = artifacts[name]
        print("\t".join((name, artifact["file"], artifact["sha256"], artifact["image"], artifact["image_id"])))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-offline")
    create.add_argument("--release-sha", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--backend-archive", required=True)
    create.add_argument("--backend-image", required=True)
    create.add_argument("--backend-image-id", required=True)
    create.add_argument("--web-archive", required=True)
    create.add_argument("--web-image", required=True)
    create.add_argument("--web-image-id", required=True)
    create.set_defaults(handler=command_create)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--release-sha", required=True)
    validate.add_argument("--artifact-dir", required=True)
    validate.set_defaults(handler=command_validate)
    metadata = subparsers.add_parser("metadata")
    metadata.add_argument("--manifest", required=True)
    metadata.add_argument("--release-sha", required=True)
    metadata.add_argument("--artifact-dir", required=True)
    metadata.set_defaults(handler=command_metadata)
    args = parser.parse_args()
    try:
        return args.handler(args)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
