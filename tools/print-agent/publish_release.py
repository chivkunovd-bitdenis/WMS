"""Publish a WMS Print release without replacing assets in an existing release.

GitHub CLI's ``release upload --clobber`` deletes an existing asset before its
replacement is uploaded.  A retry must instead prove that the already-public
release is the same immutable bundle, or stop without modifying it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


EXPECTED_ASSET_NAMES = frozenset(
    {
        "WMS-Print-Installation.md",
        "WMS-Print-Setup-Windows-x64.exe",
        "WMS-Print-Setup-Windows-x64.exe.sha256",
        "WMS-Print-SHA256SUMS.txt",
        "WMS-Print-macOS.zip",
        "WMS-Print-macOS.zip.sha256",
    }
)


def run_gh(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*shlex.split(os.environ.get("WMS_PRINT_GH", "gh")), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as asset:
        for chunk in iter(lambda: asset.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_metadata(tag: str) -> dict[str, object] | None:
    result = run_gh("release", "view", tag, "--json", "isDraft,targetCommitish,assets", check=False)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Could not inspect release {tag}.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"GitHub CLI returned invalid release metadata: {error}") from error


def expected_assets(assets_dir: Path) -> dict[str, Path]:
    assets = {asset.name: asset for asset in assets_dir.iterdir() if asset.is_file()}
    if set(assets) != EXPECTED_ASSET_NAMES:
        raise RuntimeError(
            "Refusing to publish an unexpected asset set: "
            f"expected {sorted(EXPECTED_ASSET_NAMES)}, got {sorted(assets)}."
        )
    return assets


def verify_existing_release(
    tag: str, source_commit: str, metadata: dict[str, object], assets: dict[str, Path]
) -> None:
    if metadata.get("targetCommitish") != source_commit:
        raise RuntimeError(
            f"Release {tag} targets {metadata.get('targetCommitish')!r}, not source commit {source_commit}."
        )
    published_assets = metadata.get("assets")
    if not isinstance(published_assets, list):
        raise RuntimeError(f"Release {tag} has no readable asset list.")
    published_names = {
        asset.get("name") for asset in published_assets if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    if published_names != set(assets):
        raise RuntimeError(
            f"Release {tag} asset set differs from this build; refusing to replace it. "
            f"Published {sorted(published_names)}, expected {sorted(assets)}."
        )

    with tempfile.TemporaryDirectory(prefix="wms-print-release-") as temporary_directory:
        download_dir = Path(temporary_directory)
        for name, local_asset in assets.items():
            result = run_gh("release", "download", tag, "--pattern", name, "--dir", str(download_dir), check=False)
            downloaded_asset = download_dir / name
            if result.returncode or not downloaded_asset.is_file():
                raise RuntimeError(
                    f"Could not safely verify existing asset {name} for {tag}: {result.stderr.strip()}"
                )
            if sha256(downloaded_asset) != sha256(local_asset):
                raise RuntimeError(
                    f"Release {tag} asset {name} differs from this build; refusing to replace it."
                )


def publish(tag: str, source_commit: str, assets_dir: Path, notes_file: Path) -> None:
    assets = expected_assets(assets_dir)
    metadata = release_metadata(tag)
    if metadata is None:
        create = run_gh(
            "release",
            "create",
            tag,
            "--target",
            source_commit,
            "--title",
            f"WMS Print {tag}",
            "--notes-file",
            str(notes_file),
            "--draft",
            *(str(assets[name]) for name in sorted(assets)),
            check=False,
        )
        if create.returncode:
            raise RuntimeError(create.stderr.strip() or f"Could not create draft release {tag}.")
        metadata = release_metadata(tag)
        if metadata is None:
            raise RuntimeError(f"Draft release {tag} was not found after creation.")

    verify_existing_release(tag, source_commit, metadata, assets)
    if metadata.get("isDraft") is True:
        publish_result = run_gh("release", "edit", tag, "--draft=false", check=False)
        if publish_result.returncode:
            raise RuntimeError(publish_result.stderr.strip() or f"Could not publish complete draft release {tag}.")
        print(f"Published complete draft release {tag}.")
    else:
        print(f"Existing public release {tag} already matches this immutable build; left unchanged.")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--notes-file", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    try:
        publish(arguments.tag, arguments.source_commit, arguments.assets_dir, arguments.notes_file)
    except RuntimeError as error:
        raise SystemExit(f"WMS Print release was not modified: {error}") from error


if __name__ == "__main__":
    main()
