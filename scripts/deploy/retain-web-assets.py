#!/usr/bin/env python3
"""Retain previous static assets without replacing any candidate bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def asset_files(root: Path) -> dict[str, str]:
    files = {}
    for prefix in ('assets', 'seller/assets'):
        directory = root / prefix
        parts = Path(prefix).parts
        if any((root.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts) + 1)):
            raise ValueError(f'Symlink in static asset path: {prefix}')
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ValueError(f'Asset directory must be regular: {prefix}')
        for path in sorted(directory.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Symlink in static assets: {path.relative_to(root)}')
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f'Non-regular asset: {path.relative_to(root)}')
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def prepare(previous: Path, candidate: Path, delta: Path, manifest: Path) -> int:
    old, new = asset_files(previous), asset_files(candidate)
    conflicts = sorted(name for name in old.keys() & new.keys() if old[name] != new[name])
    if conflicts:
        raise ValueError('Existing asset path has different bytes: ' + ', '.join(conflicts))
    if delta.exists() and any(delta.iterdir()):
        raise ValueError('Asset delta directory must be empty')
    delta.mkdir(parents=True, exist_ok=True)
    added = sorted(old.keys() - new.keys())
    for name in added:
        target = delta / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(previous / name, target)
    manifest.write_text(json.dumps({'previous': old, 'candidate': new, 'added': added}, indent=2) + '\n')
    return len(added)


def verify(candidate: Path, manifest: Path) -> None:
    expected = json.loads(manifest.read_text())
    actual = asset_files(candidate)
    if actual != {**expected['previous'], **expected['candidate']}:
        raise ValueError('Retained image asset checksums differ from previous/candidate union')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('prepare')
    for name in ('previous', 'candidate', 'delta', 'manifest'):
        create.add_argument('--' + name, type=Path, required=True)
    check = sub.add_parser('verify')
    for name in ('candidate', 'manifest'):
        check.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.previous, args.candidate, args.delta, args.manifest))
    else:
        verify(args.candidate, args.manifest)
        print('Previous and candidate asset checksums verified')


if __name__ == '__main__':
    main()
