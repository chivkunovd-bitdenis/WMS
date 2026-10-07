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

    def verify_anchor(self, pin):
        return anchor.verify_pr_evidence(self.f.get, self.f.download, REPO, 7,
                                         approved_bootstrap=pin)

    def verify_integrity(self, pin):
        if pin is None:
            return process_contracts.verify_integrity(self.f.root, self.f.base)
        return process_contracts.verify_integrity(self.f.root, self.f.base, approved_upgrade=pin)

    def test_exact_trusted_pin_upgrades_existing_base_and_checks_source_candidate_and_proof(self):
        checker = self.f.root / 'trusted-main/scripts/ci/trusted_process_check.py'
        self.f.write('trusted-main/scripts/ci/process_bootstrap.json', json.dumps(self.f.pin()))
        with patch.object(anchor, '__file__', str(checker)):
            trusted_pin = anchor.load_approved_bootstrap()
        policy, tree, source = anchor.baseline_policy(
            self.f.get, f'repos/{REPO}', self.f.base, trusted_pin)
        self.assertEqual(source, self.f.source)
        self.assertEqual(policy, self.f.source_policy)
        self.assertIn('tests/undo.py', tree)
        result = self.verify_anchor(self.f.pin())
        self.assertTrue(result['evidence_complete'])
        self.assertEqual(result['base_sha'], self.f.base)
        self.assertEqual(result['bootstrap_source_sha'], self.f.source)
        self.f.policy['files']['tests/scan.py'] = '9' * 64
        self.f.save_policy(self.f.policy)
        self.f.head = self.f.commit('candidate self-approved hash')
        self.f.merge = self.f.commit('merge of self-approved candidate')
        self.f.bind_candidate()
        with self.assertRaises(ValueError):
            self.verify_anchor(self.f.pin())

    def test_git_integrity_exact_approved_upgrade_accepts_reviewed_digest_and_additions(self):
        with self.assertRaisesRegex(ValueError, 'Changed protected contract hash'):
            self.verify_integrity(None)
        self.assertEqual(self.verify_integrity(self.f.pin()), self.f.source_policy)

    def test_unapproved_base_source_or_candidate_config_cannot_authorize_upgrade(self):
        self.f.write('scripts/ci/process_bootstrap.json', json.dumps(self.f.pin()))
        trusted_checker = self.f.root / 'trusted-main/scripts/ci/trusted_process_check.py'
        with patch.object(anchor, '__file__', str(trusted_checker)), patch.dict(
            'os.environ', {'SOURCE_SHA': self.f.source,
                           'PROCESS_BOOTSTRAP_CONFIG': str(self.f.root / 'scripts/ci/process_bootstrap.json')}):
            self.assertIsNone(anchor.load_approved_bootstrap())
            with self.assertRaises(ValueError):
                self.verify_anchor(anchor.load_approved_bootstrap())
            with self.assertRaises(ValueError):
                self.verify_integrity(None)
        for pin in [{'base_sha': self.f.other, 'source_sha': self.f.source},
                    {'base_sha': self.f.base, 'source_sha': self.f.other}]:
            with self.subTest(pin=pin):
                with self.assertRaises(ValueError):
                    self.verify_anchor(pin)
                with self.assertRaises(ValueError):
                    self.verify_integrity(pin)

    def test_reviewed_source_must_keep_every_base_path_case_and_suite_semantics(self):
        original = copy.deepcopy(self.f.source_policy)
        for mutation in ('path', 'case', 'report', 'format', 'exact'):
            with self.subTest(mutation=mutation):
                policy = copy.deepcopy(original)
                suite = policy['suites']['picking']
                if mutation == 'path':
                    policy['files'].pop('tests/scan.py')
                elif mutation == 'case':
                    suite['cases'].remove('tests.scan::retry')
                elif mutation == 'report':
                    suite['report'] = 'other.xml'
                elif mutation == 'format':
                    suite['format'] = 'vitest'
                else:
                    suite['exact'] = False
                self.f.save_policy(policy)
                self.f.source = self.f.commit('invalid reviewed source ' + mutation)
                self.f.head = self.f.commit('candidate equals invalid source')
                self.f.merge = self.f.commit('merge equals invalid source')
                self.f.bind_candidate()
                with self.assertRaises(ValueError):
                    self.verify_anchor(self.f.pin())
                with self.assertRaises(ValueError):
                    self.verify_integrity(self.f.pin())

    def test_corrupt_base_or_source_bytes_never_fall_back_to_candidate_hashes(self):
        for ref in ('base', 'source'):
            with self.subTest(ref=ref):
                self.f = ReviewedUpgradeFixture(Path(self.temp.name) / ref)
                self.f.git('checkout', '-q', getattr(self.f, ref))
                self.f.write('tests/scan.py', 'changed without updating saved digest\n')
                setattr(self.f, ref, self.f.commit('corrupt ' + ref + ' bytes'))
                self.f.git('checkout', '-q', self.f.head)
                self.f.bind_candidate()
                with self.assertRaises(ValueError):
                    anchor.baseline_policy(self.f.get, f'repos/{REPO}', self.f.base, self.f.pin())
                with self.assertRaises(ValueError):
                    self.verify_integrity(self.f.pin())


if __name__ == '__main__':
    unittest.main()
