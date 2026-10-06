#!/usr/bin/env python3
"""Check a whole candidate against a reference selected by a trusted caller.

This does not approve a product reference or infer permission from task documents.
The release coordinator/independent gate must select an accepted reference.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath


def product_path(name: str) -> bool:
    if name.startswith(('backend/app/', 'backend/alembic/')):
        return not any(part in {'__pycache__', '.pytest_cache'} for part in PurePosixPath(name).parts)
    if not name.startswith('frontend/'):
        return False
    parts = PurePosixPath(name).parts
    if len(parts) < 2:
        return False
    if parts[1] in {'node_modules', 'dist', 'coverage', '.vite', 'tests', 'tests-e2e', 'test-results', 'playwright-report'}:
        return False
    return not re.search(r'\.test\.[cm]?[jt]sx?$', name)


def verify_product_scope(root: Path, trusted_ref: str) -> list[str]:
    """Return every changed product path, including index and ignored new source."""
    if not isinstance(trusted_ref, str) or not trusted_ref.strip():
        raise ValueError('A separately reviewed product reference is required')

    def git(*args: str) -> bytes:
        try:
            return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError('Product scope cannot verify the candidate Git history') from exc

    root = root.resolve()
    if Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise ValueError('Product scope requires the repository root')
    head = git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    reference = git('rev-parse', '--verify', '--end-of-options', trusted_ref + '^{commit}').decode().strip()
    if git('ls-files', '--unmerged', '-z'):
        raise ValueError('Resolve the candidate index before checking its product scope')
    paths: set[str] = set()
    for args in [
        ('diff', '--no-ext-diff', '--no-textconv', '--name-only', '--no-renames', '-z', reference, head, '--'),
        ('diff', '--no-ext-diff', '--no-textconv', '--name-only', '--no-renames', '-z', head, '--'),
        ('diff', '--no-ext-diff', '--no-textconv', '--name-only', '--no-renames', '--cached', '-z', head, '--'),
    ]:
        paths.update(git(*args).decode().split('\0'))
    # Exclude generated/dependency directories by pathspec, not .gitignore. A new
    # ignored runtime source must still be observed; dependencies need no walk.
    paths.update(git('ls-files', '--others', '-z', '--', 'backend/app', 'backend/alembic', 'frontend',
        ':(exclude)frontend/node_modules', ':(exclude)frontend/dist', ':(exclude)frontend/coverage',
        ':(exclude)frontend/.vite', ':(exclude)frontend/tests', ':(exclude)frontend/tests-e2e',
        ':(exclude)frontend/test-results', ':(exclude)frontend/playwright-report',
        ':(exclude)**/__pycache__').decode().split('\0'))
    if git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip() != head:
        raise ValueError('Candidate HEAD changed during product scope verification')
    return sorted(path for path in paths if path and product_path(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--trusted-ref', required=True)
    args = parser.parse_args()
    try:
        forbidden = verify_product_scope(args.root, args.trusted_ref)
    except ValueError as exc:
        print(str(exc))
        return 2
    print(json.dumps({'unapproved_product_paths': forbidden}, ensure_ascii=False))
    return 1 if forbidden else 0


if __name__ == '__main__':
    raise SystemExit(main())
