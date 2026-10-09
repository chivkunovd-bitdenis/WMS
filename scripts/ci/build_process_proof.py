#!/usr/bin/env python3
"""Verify that every required product scenario is present and passed in this CI run.

Per-attempt evidence receipts were removed on purpose: CI blocks on real product
failures only. Missing, skipped, duplicated or failed required cases still fail here.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.process_contracts import POLICY_PATH, verify_integrity, verify_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', sha) or not re.fullmatch('[0-9a-f]{40}', args.base):
        raise ValueError('Exact head and base SHA are required')
    baseline_has_policy = subprocess.run(
        ['git', 'cat-file', '-e', f'{args.base}:{POLICY_PATH}'], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    policy = verify_integrity(root, args.base, bootstrap=not baseline_has_policy)
    results = verify_reports(policy, args.reports, sha=sha)
    print(json.dumps({name: len(cases) for name, cases in results.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
