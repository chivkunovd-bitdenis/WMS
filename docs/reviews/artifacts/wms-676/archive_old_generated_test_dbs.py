"""Archive and byte-verify only old, untracked, unopened pytest SQLite files."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

ROOT = Path('/Users/deniscivkunov/Projects/WMS')
ARCHIVE = ROOT / f'.worktrees/wms676-sol61-pipeline/tmp/old-generated-tests-{time.time_ns()}.tar.gz'
CUTOFF = time.time() - 2 * 3600


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def opened() -> set[str]:
    result = subprocess.run(['lsof', '-n', '-P', '-u', str(os.getuid()), '-Fn'],
                            capture_output=True, text=True, check=True)
    return {line[1:] for line in result.stdout.splitlines() if line.startswith('n/')}


def main() -> None:
    assert not ARCHIVE.exists(), 'Never replace an existing archive'
    files = subprocess.check_output(
        ['rg', '--files', '--hidden', '--no-ignore', '.worktrees', '-g', 'wms_pytest_*.sqlite'],
        cwd=ROOT, text=True).splitlines()
    handles = opened()
    tracked: dict[Path, set[str]] = {}
    chosen: list[tuple[Path, int, int, str]] = []
    for relative in files:
        path = ROOT / relative
        if not re.fullmatch(r'wms_pytest_[A-Za-z0-9_]+\.sqlite', path.name):
            continue
        if path.is_symlink() or path.parent.name != 'tests' or path.parent.parent.name != 'backend':
            continue
        stat = path.stat()
        if stat.st_mtime >= CUTOFF or str(path) in handles:
            continue
        tree = path.parent.parent.parent
        if tree not in tracked:
            tracked[tree] = set(subprocess.check_output(
                ['git', 'ls-files', 'backend/tests'], cwd=tree, text=True).splitlines())
        if path.relative_to(tree).as_posix() in tracked[tree]:
            continue
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                continue
        if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            continue
        chosen.append((path, stat.st_size, stat.st_mtime_ns, digest(path)))
        if len(chosen) >= 75:
            break
    assert chosen, 'No eligible generated databases'
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(ARCHIVE, 'x:gz') as archive:
        for path, _, _, _ in chosen:
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        for path, _, _, expected in chosen:
            stream = archive.extractfile(path.relative_to(ROOT).as_posix())
            assert stream is not None
            with stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, path
    # Verify a second fresh handle snapshot and original bytes before each removal.
    handles = opened()
    removed = 0
    freed = 0
    for path, size, mtime_ns, expected in chosen:
        stat = path.stat()
        if str(path) in handles or stat.st_size != size or stat.st_mtime_ns != mtime_ns:
            continue
        if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            continue
        assert digest(path) == expected, path
        path.unlink()
        removed += 1
        freed += size
    print({'archive': str(ARCHIVE), 'sha256': digest(ARCHIVE),
           'archived_count': len(chosen), 'removed_count': removed,
           'freed_bytes': freed, 'archive_bytes': ARCHIVE.stat().st_size})


if __name__ == '__main__':
    main()
