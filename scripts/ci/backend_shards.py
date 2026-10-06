#!/usr/bin/env python3
"""Two complete backend shards with exact collection and attempt-bound JUnit."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def partition(collection, index):
    if type(index) is not int or index not in (0, 1):
        raise ValueError('Exactly two shard indices, 0 and 1, are supported')
    if (not isinstance(collection, list) or not collection or
            any(not isinstance(node, str) or not node or '\n' in node for node in collection) or
            len(collection) != len(set(collection))):
        raise ValueError('Full unique nonempty pytest collection required')
    return sorted(collection)[index::2]


def digest(collection):
    return hashlib.sha256(json.dumps(sorted(collection), ensure_ascii=False).encode()).hexdigest()


def pytest_collection_modifyitems(config, items):
    """Loaded in every xdist worker; compare full collection before deselection."""
    if 'WMS_BACKEND_SHARD_INDEX' not in os.environ:
        return
    full = [item.nodeid for item in items]
    selected = set(partition(full, int(os.environ['WMS_BACKEND_SHARD_INDEX'])))
    if digest(full) != os.environ['WMS_BACKEND_COLLECTION_DIGEST']:
        raise ValueError('Worker collection differs from the complete controller collection')
    discarded = [item for item in items if item.nodeid not in selected]
    items[:] = [item for item in items if item.nodeid in selected]
    for item in items:
        item.user_properties.append(('wms_nodeid', item.nodeid))
    config.hook.pytest_deselected(items=discarded)


def attempt_identity():
    result = {'sha': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
              'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT'])}
    validate_identity(result)
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        if actual != result['sha']:
            raise ValueError('Checked out backend differs from this CI attempt SHA')
    return result


def validate_identity(data):
    if (not re.fullmatch('[0-9a-f]{40}', data['sha']) or
            any(type(data[key]) is not int or data[key] < 1 for key in ('run_id', 'run_attempt'))):
        raise ValueError('Exact tested SHA/run/attempt required')


def run(index, output, arguments):
    # xdist freezes sys.path when its plugin is first imported. Establish the
    # repository import path before importing pytest/collecting, for all workers.
    root = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, root)
    os.environ['PYTHONPATH'] = root + os.pathsep + os.environ.get('PYTHONPATH', '')
    import pytest

    class Collection:
        def __init__(self):
            self.ids = []

        def pytest_collection_finish(self, session):
            self.ids = [item.nodeid for item in session.items]

    identity = attempt_identity()
    output.mkdir(parents=True, exist_ok=False)
    capture = Collection()
    code = pytest.main([*arguments, '--collect-only', '-n', '0'], plugins=[capture])
    if code != 0:
        raise ValueError('Full backend collection failed; do not execute a partial shard')
    full = sorted(capture.ids)
    selected = partition(full, index)
    os.environ['WMS_BACKEND_SHARD_INDEX'] = str(index)
    os.environ['WMS_BACKEND_COLLECTION_DIGEST'] = digest(full)
    code = int(pytest.main([*arguments, '-p', 'scripts.ci.backend_shards',
                           '--junitxml=' + str(output / 'junit.xml')]))
    receipt = {**identity, 'version': 1, 'count': 2, 'index': index,
               'collection': full, 'selected': selected, 'exit_code': code}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return code


def json_read(path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('Duplicate receipt key')
            result[key] = value
        return result
    raw = path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('Receipt too large')
    return json.loads(raw, object_pairs_hook=pairs)


def merge(paths, output, identity, required=()):
    validate_identity(identity)
    if len(paths) != 2:
        raise ValueError('Both backend shard artifacts are required')
    receipts, reports = {}, {}
    for path in paths:
        receipt = json_read(path / 'receipt.json')
        if (type(receipt['version']) is not int or receipt['version'] != 1 or
                type(receipt['count']) is not int or receipt['count'] != 2 or
                any(type(receipt.get(k)) is not type(v) or receipt.get(k) != v for k, v in identity.items()) or
                type(receipt['exit_code']) is not int):
            raise ValueError('Shard artifact does not belong to the exact tested attempt')
        index = receipt['index']
        expected = partition(receipt['collection'], index)
        if index in receipts or receipt['selected'] != expected:
            raise ValueError('Duplicate shard or altered deterministic selection')
        receipts[index] = receipt
        raw = (path / 'junit.xml').read_bytes()
        if len(raw) > 32 * 1024 * 1024 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
            raise ValueError('Oversized or unsafe JUnit')
        report = ET.fromstring(raw)
        if report.tag not in {'testsuites', 'testsuite'}:
            raise ValueError('JUnit report required')
        reports[index] = report
    if set(receipts) != {0, 1} or receipts[0]['collection'] != receipts[1]['collection']:
        raise ValueError('Shards did not collect the same full backend suite')
    combined = ET.Element('testsuites')
    counts = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    nodes, outcomes = set(), {}
    for index in (0, 1):
        case_errors = {error for case in reports[index].iter('testcase')
                       for error in case.iter('error')}
        counts['errors'] += sum(error not in case_errors for error in reports[index].iter('error'))
        actual = set()
        for case in reports[index].iter('testcase'):
            properties = case.findall("properties/property[@name='wms_nodeid']")
            if len(properties) != 1:
                raise ValueError('JUnit case has no unique executed pytest node ID')
            node = properties[0].get('value')
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            if node in nodes or name in outcomes:
                raise ValueError('Duplicate executed backend case')
            nodes.add(node)
            actual.add(node)
            counts['tests'] += 1
            status = 'passed'
            for tag, count in [('failure', 'failures'), ('error', 'errors'), ('skipped', 'skipped')]:
                if case.find(tag) is not None:
                    counts[count] += 1
                    status = tag
            outcomes[name] = status
        if actual != set(receipts[index]['selected']):
            raise ValueError('Executed cases differ from the exact selected shard')
        suites = [reports[index]] if reports[index].tag == 'testsuite' else list(reports[index])
        for suite in suites:
            combined.append(copy.deepcopy(suite))
    if nodes != set(receipts[0]['collection']):
        raise ValueError('Merged execution is not the full collection exactly once')
    if any(outcomes.get(name) != 'passed' for name in required):
        raise ValueError('Required backend case is missing, skipped or failed')
    for name, value in counts.items():
        combined.set(name, str(value))
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(combined).write(output, encoding='utf-8', xml_declaration=True)
    return {**counts, 'success': not (counts['failures'] or counts['errors'] or
                                     any(receipt['exit_code'] != 0 for receipt in receipts.values()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    runner = commands.add_parser('run')
    runner.add_argument('--index', type=int, required=True)
    runner.add_argument('--output', type=Path, required=True)
    runner.add_argument('arguments', nargs=argparse.REMAINDER)
    merger = commands.add_parser('merge')
    merger.add_argument('--shards', type=Path, nargs=2, required=True)
    merger.add_argument('--output', type=Path, required=True)
    merger.add_argument('--policy', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
            return run(args.index, args.output, arguments)
        policy = json_read(args.policy)
        required = [case for suite in policy['suites'].values() if suite['report'] == 'backend-all.xml'
                    for case in suite['cases']]
        if not required:
            raise ValueError('Protected full-backend named cases required')
        result = merge(args.shards, args.output, attempt_identity(), required=required)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['success'] else 2
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError):
        print('Full backend shard evidence missing, failed or inconsistent', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
