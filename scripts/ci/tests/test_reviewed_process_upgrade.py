"""WMS-652: exact trusted-main BASE/SOURCE upgrade, frozen before code.

The GitHub boundary serves real temporary Git objects; validators are not mocked.
"""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlparse

from scripts.ci import process_contracts, trusted_process_check as anchor
from scripts.ci.tests.test_trusted_process_artifact import ArtifactFixture
from scripts.ci.tests.test_trusted_process_check import REPO


class ReviewedUpgradeFixture(ArtifactFixture):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('.github/workflows/ci.yml', 'name: CI\n')
        self.write('tests/scan.py', 'def scan(): return 1\n')
        self.base_policy = {'version': 1, 'files': {}, 'suites': {
            'picking': {'report': 'picking.xml', 'format': 'junit', 'exact': True,
                        'cases': ['tests.scan::scan', 'tests.scan::retry']}}}
        self.save_policy(self.base_policy, ['.github/workflows/ci.yml', 'tests/scan.py'])
        self.base = self.commit('existing BASE policy')
        self.other = self.commit('unapproved unchanged source')
        self.write('tests/scan.py', 'def scan(): return 2\n')
        self.write('tests/undo.py', 'def undo(): return 1\n')
        self.source_policy = copy.deepcopy(self.base_policy)
        self.source_policy['suites']['picking']['cases'].append('tests.undo::undo')
        self.save_policy(self.source_policy, ['tests/scan.py', 'tests/undo.py'])
        self.source = self.commit('reviewed changed digest and additive file/case')
        self.head = self.commit('candidate equals reviewed source')
        self.merge = self.commit('tested merge equals candidate')
        self.bind_candidate()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args],
                                       stderr=subprocess.PIPE)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')

    def save_policy(self, policy, paths=()):
        for name in paths:
            policy['files'][name] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.write(anchor.POLICY_PATH, json.dumps(policy))

    def commit(self, title):
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-qm', title)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def bind_candidate(self):
        self.policy = json.loads(self.git('show', f'{self.head}:{anchor.POLICY_PATH}'))
        self.pr['base']['sha'] = self.base
        self.pr['head']['sha'] = self.head
        self.pr['merge_commit_sha'] = self.merge
        self.run['head_sha'] = self.head
        self.run['pull_requests'][0]['head']['sha'] = self.head
        self.run['pull_requests'][0]['base']['sha'] = self.base
        for job in self.jobs:
            job['head_sha'] = self.head
        self.artifacts[0]['name'] = f'process-proof-{self.merge}-10-1'
        self.artifacts[0]['workflow_run']['head_sha'] = self.head
        self.metadata.update(sha=self.merge, head_sha=self.head, base_sha=self.base,
                             policy_sha256=self.digest())

    def pin(self):
        return {'base_sha': self.base, 'source_sha': self.source}

    def get(self, path):
        route = unquote(path.split('?')[0])
        prefix = f'repos/{REPO}/'
        if route.startswith(prefix + 'git/commits/'):
            self.paths.append(path)
            ref = route.rsplit('/', 1)[-1]
            return {'tree': {'sha': self.git('rev-parse', f'{ref}^{{tree}}').decode().strip()}}
        if route.startswith(prefix + 'git/trees/'):
            self.paths.append(path)
            ref = route.rsplit('/', 1)[-1]
            rows = []
            for line in self.git('ls-tree', '-r', ref).decode().splitlines():
                metadata, name = line.split('\t', 1)
                mode, kind, digest = metadata.split()
                rows.append({'path': name, 'mode': mode, 'type': kind, 'sha': digest})
            return {'truncated': False, 'tree': rows}
        if route.startswith(prefix + 'git/blobs/'):
            self.paths.append(path)
            raw = self.git('cat-file', 'blob', route.rsplit('/', 1)[-1])
            return {'encoding': 'base64', 'content': base64.b64encode(raw).decode(),
                    'size': len(raw)}
        if route.startswith(prefix + 'contents/'):
            self.paths.append(path)
            name = route[len(prefix + 'contents/'):]
            ref = parse_qs(urlparse(path).query)['ref'][0]
            raw = self.git('show', f'{ref}:{name}')
            return {'path': name, 'encoding': 'base64',
                    'sha': self.git('rev-parse', f'{ref}:{name}').decode().strip(),
                    'content': base64.b64encode(raw).decode(), 'size': len(raw)}
        if '/check-suites/' in route:
            self.paths.append(path)
            return {'app': {'id': 15368, 'slug': 'github-actions'}, 'head_sha': self.head}
        return super().get(path)


class ReviewedProcessUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ReviewedUpgradeFixture(Path(self.temp.name))

    def verify_anchor(self):
        return anchor.verify_pr_evidence(self.f.get, self.f.download, REPO, 7,
                                         approved_bootstrap=None)

    def verify_integrity(self):
        return process_contracts.verify_integrity(self.f.root, self.f.base)

    def test_source_and_fixture_changes_pass_without_external_pin(self):
        policy, _, source = anchor.baseline_policy(self.f.get, f'repos/{REPO}', self.f.base, None)
        self.assertIsNone(source)
        self.assertEqual(policy, self.f.base_policy)
        result = self.verify_anchor()
        self.assertTrue(result['evidence_complete'])
        self.assertEqual(result['base_sha'], self.f.base)
        self.assertNotIn('bootstrap_source_sha', result)
        self.assertEqual(self.verify_integrity(), self.f.policy)

    def test_rename_and_addition_are_reviewable_when_mandatory_counts_remain(self):
        self.f.git('mv', 'tests/scan.py', 'tests/renamed_scan.py')
        self.f.policy['files'].pop('tests/scan.py')
        self.f.policy['files']['tests/renamed_scan.py'] = '9' * 64
        self.f.save_policy(self.f.policy)
        self.f.head = self.f.commit('candidate renamed source')
        self.f.merge = self.f.commit('merge renamed source')
        self.f.bind_candidate()
        self.assertTrue(self.verify_anchor()['evidence_complete'])
        self.assertEqual(self.verify_integrity(), self.f.policy)

    def test_case_rename_is_accepted_but_decreased_suite_coverage_fails(self):
        self.f.policy['suites']['picking']['cases'][0] = 'tests.scan::renamed'
        self.f.save_policy(self.f.policy)
        self.f.head = self.f.commit('rename required case')
        self.f.merge = self.f.commit('merge renamed case')
        self.f.bind_candidate()
        self.assertTrue(self.verify_anchor()['evidence_complete'])
        self.assertEqual(self.verify_integrity(), self.f.policy)

        self.f.policy['suites']['picking']['cases'].pop()
        self.f.policy['suites']['picking']['cases'].pop()
        self.f.policy['files'].pop('tests/undo.py')
        self.f.save_policy(self.f.policy)
        self.f.head = self.f.commit('remove required case')
        self.f.merge = self.f.commit('merge missing case')
        self.f.bind_candidate()
        with self.assertRaisesRegex(ValueError, 'protected execution contract'):
            self.verify_anchor()
        with self.assertRaisesRegex(ValueError, 'case count decreased'):
            self.verify_integrity()

    def test_actual_report_missing_or_skip_remains_failure(self):
        report = self.f.root / 'picking.xml'
        report.write_text('<testsuite><testcase classname="tests.scan" name="scan"/></testsuite>')
        with self.assertRaisesRegex(ValueError, 'missing required cases'):
            process_contracts.verify_reports(self.f.policy, self.f.root)


if __name__ == '__main__':
    unittest.main()
