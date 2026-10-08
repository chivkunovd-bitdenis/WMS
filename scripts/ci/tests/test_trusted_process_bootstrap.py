"""WMS-652 owner-pinned first baseline: additive contract before implementation."""
import base64
import contextlib
import copy
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from scripts.ci.tests.test_trusted_process_artifact import ArtifactFixture
from scripts.ci.tests.test_trusted_process_check import REPO, B, H, M

S = 'd' * 40
PIN = {'base_sha': B, 'source_sha': S}


class BootstrapFixture(ArtifactFixture):
    def __init__(self):
        super().__init__()
        self.base_tree = [row for row in self.base_tree
                          if row['path'] != 'guards/PROCESS_CONTRACTS.json']
        self.tree = copy.deepcopy(self.base_tree)
        self.source_policy = copy.deepcopy(self.base_policy)
        self.source_tree = copy.deepcopy(self.base_tree)
        self.policy_row = {'path': 'guards/PROCESS_CONTRACTS.json', 'type': 'blob',
                           'mode': '100644', 'sha': self.blob_oid(json.dumps(self.source_policy).encode())}
        self.tree.append(copy.deepcopy(self.policy_row))
        self.source_tree.append(copy.deepcopy(self.policy_row))
        self.missing_base = True
        self.source_available = True
        self.tree_outage = False
        self.policy_outage = False

    @staticmethod
    def blob_oid(raw):
        import hashlib
        return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

    def get(self, path):
        route = path.split('?')[0]
        if '/git/trees/' in route:
            ref = route.rsplit('/', 1)[-1]
            if self.tree_outage and ref == B:
                raise ValueError('synthetic API outage')
            if ref == S:
                self.paths.append(path)
                if not self.source_available:
                    raise ValueError('reviewed source unavailable')
                return {'truncated': False, 'tree': copy.deepcopy(self.source_tree)}
            if ref == B:
                self.paths.append(path)
                rows = copy.deepcopy(self.base_tree)
                if not self.missing_base:
                    rows.append(copy.deepcopy(self.policy_row))
                return {'truncated': self.truncated, 'tree': rows}
        if '/contents/guards/PROCESS_CONTRACTS.json' in route:
            ref = parse_qs(urlparse(path).query)['ref'][0]
            if ref == B and (self.missing_base or self.policy_outage):
                raise ValueError('baseline policy unavailable')
            if ref == S:
                self.paths.append(path)
                if not self.source_available:
                    raise ValueError('reviewed source unavailable')
                return {'path': 'guards/PROCESS_CONTRACTS.json', 'encoding': 'base64',
                    'content': base64.b64encode(json.dumps(self.source_policy).encode()).decode()}
        return super().get(path)


class ExplicitBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.trusted_process_check')
        self.f = BootstrapFixture()

    def verify(self, pin=PIN):
        return self.m.verify_pr_evidence(self.f.get, self.f.download, REPO, 7,
                                         approved_bootstrap=pin)

    def reject(self, pin=PIN):
        with self.assertRaises(ValueError):
            self.verify(pin)

    def test_missing_policy_only_exact_explicit_pin_accepts_with_real_ci_base(self):
        result = self.verify()
        self.assertTrue(result['evidence_complete'])
        self.assertEqual((result['head_sha'], result['base_sha'], result['merge_sha']), (H, B, M))
        self.assertEqual(result['bootstrap_source_sha'], S)
        self.assertIn(f'repos/{REPO}/git/trees/{S}?recursive=1', self.f.paths)
        self.assertIn(f'repos/{REPO}/contents/guards/PROCESS_CONTRACTS.json?ref={S}', self.f.paths)
        self.f.metadata['base_sha'] = S
        self.reject()

    def test_no_pin_wrong_base_or_invalid_source_never_auto_bootstrap(self):
        for pin in [None, {}, {'base_sha': 'e'*40, 'source_sha': S},
                    {'base_sha': B, 'source_sha': 'main'},
                    {'base_sha': B, 'source_sha': B},
                    {**PIN, 'allow': True}, {'base_sha': B}]:
            with self.subTest(pin=pin):
                self.f = BootstrapFixture()
                self.reject(pin)

    def test_seed_api_unavailable_missing_policy_or_truncated_tree_refuses(self):
        for mutation in ['unavailable', 'missing-policy', 'base-tree-outage', 'truncated']:
            with self.subTest(mutation=mutation):
                self.f = BootstrapFixture()
                if mutation == 'unavailable': self.f.source_available = False
                elif mutation == 'missing-policy': self.f.source_tree.pop()
                elif mutation == 'base-tree-outage': self.f.tree_outage = True
                else: self.f.truncated = True
                self.reject()

    def test_seed_still_requires_sources_and_suite_but_legacy_hash_is_not_a_lock(self):
        for mutation in ['blob', 'missing']:
            with self.subTest(mutation=mutation):
                self.f = BootstrapFixture()
                if mutation == 'blob':
                    next(row for row in self.f.source_tree if row['path'] == 'tests/scan.py')['sha'] = 'invalid'
                elif mutation == 'missing':
                    self.f.source_tree = [row for row in self.f.source_tree if row['path'] != 'tests/scan.py']
                self.reject()

    def test_regular_source_mode_and_legacy_digest_changes_do_not_require_pin(self):
        next(row for row in self.f.tree if row['path'] == 'tests/scan.py')['mode'] = '100755'
        self.f.policy['files']['tests/scan.py'] = '9'*64
        self.f.metadata['policy_sha256'] = self.f.digest()
        self.assertTrue(self.verify()['evidence_complete'])

    def test_existing_baseline_priority_never_reads_seed_even_with_wrong_pin(self):
        self.f.missing_base = False
        self.f.source_available = False
        result = self.verify({'base_sha': 'e'*40, 'source_sha': S})
        self.assertTrue(result['evidence_complete'])
        self.assertNotIn('bootstrap_source_sha', result)
        self.assertFalse(any(S in path for path in self.f.paths))

    def test_existing_corrupt_policy_or_api_outage_never_replaced_by_seed(self):
        for mutation in ['outage', 'malformed']:
            with self.subTest(mutation=mutation):
                self.f = BootstrapFixture()
                self.f.missing_base = False
                if mutation == 'outage': self.f.policy_outage = True
                else: self.f.base_policy['version'] = 999
                self.reject()
                self.assertFalse(any(S in path for path in self.f.paths))

    def test_seed_does_not_exempt_required_ci_jobs_or_final_attempt_reread(self):
        self.f.jobs[-1]['conclusion'] = 'skipped'
        self.reject()
        self.f = BootstrapFixture()
        self.f.advance_attempt = True
        self.reject()

    def test_loader_absent_refuses_malformed_and_accepts_only_two_exact_sha_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            checker = Path(folder) / 'trusted_process_check.py'
            checker.touch()
            with patch.object(self.m, '__file__', str(checker)):
                self.assertIsNone(self.m.load_approved_bootstrap())
                config = checker.with_name('process_bootstrap.json')
                config.write_text(json.dumps(PIN))
                self.assertEqual(self.m.load_approved_bootstrap(), PIN)
                for body in ['not json', json.dumps({**PIN, 'allow': True}),
                             '{"base_sha":"'+B+'","base_sha":"'+B+'","source_sha":"'+S+'"}']:
                    config.write_text(body)
                    with self.assertRaises(ValueError): self.m.load_approved_bootstrap()

    def test_cli_reads_only_sibling_trusted_pin_and_still_requires_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            checker = Path(folder) / 'trusted_process_check.py'
            checker.touch()
            checker.with_name('process_bootstrap.json').write_text(json.dumps(PIN))
            argv = ['checker', '--repository', REPO, '--pr', '7']
            with patch.object(self.m, '__file__', str(checker)), patch('sys.argv', argv), \
                    patch.object(self.m, 'api_get', self.f.get), \
                    patch.object(self.m, 'download_artifact', self.f.download), \
                    patch.object(self.m, 'publish') as published, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.m.main(), 0)
                self.f.artifacts = []
                self.assertEqual(self.m.main(), 2)
                published.assert_not_called()
                self.assertFalse(any('/contents/scripts/ci/process_bootstrap.json' in p for p in self.f.paths))


if __name__ == '__main__':
    unittest.main()
