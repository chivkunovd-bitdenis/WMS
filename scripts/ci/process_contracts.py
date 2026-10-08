#!/usr/bin/env python3
"""WMS-652: retained regression coverage and actual named test execution.

This checker is not an independent GitHub enforcement anchor. CI must invoke its
trusted BASE version; deployment must separately verify run/artifact provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import xml.etree.ElementTree as ET

POLICY_PATH = 'guards/PROCESS_CONTRACTS.json'


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError('Empty or invalid relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or '\\' in value:
        raise ValueError(f'Invalid relative path: {value}')
    return value


def local_file(root: Path, name: str) -> Path:
    path = root / relative_path(name)
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'Symlink is not execution evidence: {name}')
    if not path.is_file():
        raise ValueError(f'Missing required file: {name}')
    return path


def validate_policy(policy: dict) -> None:
    if set(policy) != {'version', 'files', 'suites'} or policy['version'] != 1:
        raise ValueError('Unsupported process contract schema')
    if not isinstance(policy['files'], dict) or not isinstance(policy['suites'], dict):
        raise ValueError('Invalid files/suites')
    if not policy['suites']:
        raise ValueError('No protected process suites')
    for path, digest in policy['files'].items():
        relative_path(path)
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError(f'Invalid protected digest: {path}')
    reports = set()
    for name, suite in policy['suites'].items():
        if not re.fullmatch('[a-z0-9_-]+', name):
            raise ValueError('Invalid suite name')
        if set(suite) != {'report', 'format', 'exact', 'cases'}:
            raise ValueError(f'Invalid suite schema: {name}')
        relative_path(suite['report'])
        if suite['report'] in reports:
            raise ValueError('Two suites cannot claim the same report')
        reports.add(suite['report'])
        if suite['format'] not in {'junit', 'vitest', 'node-tap', 'browser-json'} or type(suite['exact']) is not bool:
            raise ValueError(f'Invalid suite format: {name}')
        cases = suite['cases']
        if (not isinstance(cases, list) or not cases or
                any(not isinstance(case, str) or not case.strip() for case in cases) or
                len(cases) != len(set(cases))):
            raise ValueError(f'Empty or duplicate required cases: {name}')


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def git_policy(root: Path, ref: str) -> dict:
    data = json.loads(git(root, 'show', f'{ref}:{POLICY_PATH}'))
    validate_policy(data)
    return data


def verify_integrity(root: Path, base: str, *, bootstrap: bool = False) -> dict:
    """Validate the candidate execution policy; ordinary review assesses policy changes."""
    candidate = json.loads(local_file(root, POLICY_PATH).read_bytes())
    validate_policy(candidate)
    git(root, 'cat-file', '-e', f'{base}^{{commit}}')
    paths = git(root, 'ls-tree', '--name-only', base, POLICY_PATH).decode().splitlines()
    if not paths:
        if not bootstrap:
            raise ValueError('Trusted BASE has no process policy; bootstrap acceptance required')
    else:
        git_policy(root, base)
    return candidate


def junit_results(raw: bytes) -> dict[str, str]:
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError('Malformed JUnit report') from exc
    if tree.tag not in {'testsuites', 'testsuite'}:
        raise ValueError('Invalid JUnit root')
    result = {}
    for case in tree.iter('testcase'):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        if name in result:
            raise ValueError(f'Duplicate executed case: {name}')
        status = 'passed'
        for tag in ('skipped', 'failure', 'error'):
            if case.find(tag) is not None:
                status = tag
        result[name] = status
    # A collection/setup error must not disappear when checking only a subset.
    if list(tree.iter('error')):
        raise ValueError('JUnit collection/setup/runtime error')
    return result


def vitest_results(raw: bytes) -> dict[str, str]:
    data = json.loads(raw)
    if data.get('success') is not True:
        raise ValueError('Vitest did not finish successfully')
    result = {}
    for suite in data['testResults']:
        file = suite['name'].replace('\\', '/')
        if '/frontend/' in file:
            file = file.rsplit('/frontend/', 1)[1]
        elif file.startswith('frontend/'):
            file = file[len('frontend/'):]
        relative_path(file)
        if not suite['assertionResults'] or suite.get('status') in {'failed', 'pending'}:
            raise ValueError(f'Empty or failed Vitest file: {file}')
        for case in suite['assertionResults']:
            name = f"{file}::{case['fullName']}"
            if name in result:
                raise ValueError(f'Duplicate executed case: {name}')
            result[name] = case['status']
    return result


def node_tap_results(raw: bytes) -> dict[str, str]:
    text = raw.decode('utf-8')
    result = {}
    numbers = []
    for match in re.finditer(r'^(ok|not ok) (\d+) - (.+)$', text, re.M):
        status, number, name = match.groups()
        numbers.append(int(number))
        if name in result:
            raise ValueError(f'Duplicate TAP case: {name}')
        if re.search(r'\s+#\s*(SKIP|TODO)', name, re.I):
            raise ValueError(f'Unexecuted TAP case: {name}')
        result[name] = 'passed' if status == 'ok' else 'failed'
    if not result or numbers != list(range(1, len(result) + 1)):
        raise ValueError('Incomplete TAP execution')
    if re.findall(r'^1\.\.(\d+)$', text, re.M) != [str(len(result))]:
        raise ValueError('Missing or inconsistent TAP plan')
    for key in ('fail', 'cancelled', 'skipped', 'todo'):
        if re.findall(r'^# ' + key + r' (\d+)$', text, re.M) != ['0']:
            raise ValueError(f'TAP {key} is nonzero or missing')
    return result


def browser_results(raw: bytes, sha: str | None) -> dict[str, str]:
    data = json.loads(raw)
    if not sha or data.get('sha') != sha or data.get('status') != 'PASS':
        raise ValueError('Real browser proof did not pass for the tested SHA')
    result = {}
    for case in data['cases']:
        if case['id'] in result:
            raise ValueError(f"Duplicate browser case: {case['id']}")
        result[case['id']] = 'passed' if case['status'] == 'PASS' else case['status']
    return result


def verify_reports(policy: dict, root: Path, *, sha: str | None = None) -> dict[str, list[str]]:
    validate_policy(policy)
    readers = {'junit': junit_results, 'vitest': vitest_results, 'node-tap': node_tap_results}
    verified = {}
    for name, suite in policy['suites'].items():
        raw = local_file(root, suite['report']).read_bytes()
        actual = (browser_results(raw, sha) if suite['format'] == 'browser-json'
                  else readers[suite['format']](raw))
        required = set(suite['cases'])
        missing = required - actual.keys()
        if missing:
            raise ValueError(f'{name}: missing required cases: {sorted(missing)}')
        nonpass = {case: actual[case] for case in required if actual[case] != 'passed'}
        if nonpass:
            raise ValueError(f'{name}: required cases did not pass: {nonpass}')
        if suite['exact'] and actual.keys() != required:
            raise ValueError(f'{name}: unexpected cases: {sorted(actual.keys() - required)}')
        verified[name] = suite['cases']
    return verified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--base', required=True)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--reports', type=Path)
    args = parser.parse_args()
    policy = verify_integrity(args.root, args.base, bootstrap=args.bootstrap)
    if args.reports:
        sha = git(args.root, 'rev-parse', 'HEAD').decode().strip()
        print(json.dumps(verify_reports(policy, args.reports, sha=sha), ensure_ascii=False))
    else:
        print(f"Process contract integrity: {len(policy['files'])} files")


if __name__ == '__main__':
    main()
