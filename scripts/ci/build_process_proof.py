#!/usr/bin/env python3
"""Assemble actual test reports only after exact protected-case verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.process_contracts import POLICY_PATH, verify_integrity, verify_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    head = os.environ['CANDIDATE_HEAD_SHA']
    if any(not re.fullmatch('[0-9a-f]{40}', value) for value in [sha, head, args.base]):
        raise ValueError('Exact head, tested commit and base SHA are required')
    if os.environ.get('GITHUB_SHA') != sha:
        raise ValueError('Checked out code differs from the Actions tested SHA')
    baseline_has_policy = subprocess.run(
        ['git', 'cat-file', '-e', f'{args.base}:{POLICY_PATH}'], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    policy = verify_integrity(root, args.base, bootstrap=not baseline_has_policy)
    results = verify_reports(policy, args.reports)
    output = args.reports.parent / 'process-proof-final'
    if output.exists():
        raise ValueError('Evidence output already exists; do not reuse an earlier attempt')
    output.mkdir()
    for suite in policy['suites'].values():
        target = output / suite['report']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.reports / suite['report'], target)
    metadata = dict(version=1, sha=sha, head_sha=head, base_sha=args.base,
                    run_id=int(os.environ['GITHUB_RUN_ID']),
                    run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
                    policy_sha256=hashlib.sha256((root / POLICY_PATH).read_bytes()).hexdigest())
    (output / 'execution.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({name: len(cases) for name, cases in results.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
