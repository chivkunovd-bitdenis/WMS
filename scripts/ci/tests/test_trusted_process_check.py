"""Independent default-branch anchor contract: candidate files are only data."""
import base64
import copy
import importlib
import json
import unittest
from urllib.parse import parse_qs, urlparse

H, B, M = 'a'*40, 'b'*40, 'c'*40
REPO = 'owner/repo'


class AnchorFixture:
    def __init__(self):
        self.pr = {'number': 7, 'state': 'open', 'changed_files': 1,
                   'head': {'sha': H, 'repo': {'full_name': REPO}},
                   'base': {'sha': B, 'ref': 'etalon', 'repo': {'full_name': REPO}}, 'merge_commit_sha': M}
        self.base_policy = {'version': 1, 'files': {'.github/workflows/ci.yml': '0'*64,
            '.github/workflows/deploy.yml': '1'*64, 'tests/scan.py': '2'*64},
            'suites': {'qr': {'report': 'qr.json', 'format': 'browser-json', 'exact': True, 'cases': ['first', 'next']}}}
        self.policy = copy.deepcopy(self.base_policy)
        self.base_tree = [{'path': path, 'sha': str(i)*40, 'mode': '100644', 'type': 'blob'}
                          for i, path in enumerate(self.policy['files'], 1)]
        self.base_tree.append({'path': 'guards/PROCESS_CONTRACTS.json', 'sha': 'f'*40,
                               'mode': '100644', 'type': 'blob'})
        self.tree = copy.deepcopy(self.base_tree)
        self.run = {'id': 10, 'run_number': 5, 'run_attempt': 1, 'head_sha': H,
                    'event': 'pull_request', 'workflow_id': 6, 'path': '.github/workflows/ci.yml',
                    'repository': {'full_name': REPO}, 'head_repository': {'full_name': REPO},
                    'status': 'completed', 'conclusion': 'success', 'check_suite_id': 20,
                    'pull_requests': [{'number': 7, 'head': {'sha': H}, 'base': {'sha': B}}]}
        self.runs = [self.run]
        self.jobs = [{'id': i, 'name': name, 'status': 'completed', 'conclusion': 'success',
                     'run_id': 10, 'head_sha': H} for i, name in enumerate([
            'baseline', 'backlog', 'scope', 'backend', 'frontend-build', 'охрана',
            'print-regressions', 'printer-windows', 'wms686-mockup', 'process-proof'], 1)]
        self.pr_reads = 0
        self.change_head_after = False
        self.truncated = False
        self.bootstrap = False
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        route = path.split('?')[0]
        if route.endswith('/pulls/7'):
            self.pr_reads += 1
            if self.change_head_after and self.pr_reads > 1:
                self.pr['head']['sha'] = 'd'*40
            return copy.deepcopy(self.pr)
        if '/pulls/7/files' in route:
            return [{'filename': 'frontend/src/app.ts'}]
        if '/contents/guards/PROCESS_CONTRACTS.json' in route:
            ref = parse_qs(urlparse(path).query)['ref'][0]
            if self.bootstrap and ref == B: raise ValueError('no trusted baseline policy')
            policy = self.base_policy if ref == B else self.policy
            return {'path': 'guards/PROCESS_CONTRACTS.json', 'encoding': 'base64',
                    'content': base64.b64encode(json.dumps(policy).encode()).decode()}
        if '/git/commits/' in route:
            return {'tree': {'sha': route.rsplit('/', 1)[-1]}}
        if '/git/trees/' in route:
            sha = route.rsplit('/', 1)[-1]
            return {'truncated': self.truncated, 'tree': copy.deepcopy(self.base_tree if sha == B else self.tree)}
        if route.endswith('/workflows/ci.yml'):
            return {'id': 6, 'path': '.github/workflows/ci.yml', 'state': 'active'}
        if '/workflows/6/runs' in route:
            return {'total_count': len(self.runs), 'workflow_runs': copy.deepcopy(self.runs)}
        if '/jobs' in route:
            return {'total_count': len(self.jobs), 'jobs': copy.deepcopy(self.jobs)}
        if '/check-suites/' in route:
            return {'app': {'id': 15368, 'slug': 'github-actions'}, 'head_sha': H}
        raise AssertionError(path)


class TrustedProcessCheckTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.trusted_process_check')
        self.f = AnchorFixture()

    def verify(self): return self.m.verify_pr(self.f.get, REPO, 7)

    def test_same_code_complete_exact_ci_is_accepted(self):
        self.assertEqual(self.verify()['head_sha'], H)
        self.assertGreaterEqual(self.f.pr_reads, 2)

    def test_source_digest_metadata_can_change_under_ordinary_review(self):
        for path in self.f.policy['files']:
            with self.subTest(path=path):
                self.f = AnchorFixture()
                self.f.policy['files'][path] = '9'*64
                next(row for row in self.f.tree if row['path'] == path)['sha'] = 'e'*40
                self.assertEqual(self.verify()['head_sha'], H)

    def test_source_bytes_can_change_without_pin_when_path_and_coverage_remain(self):
        self.f.tree[-1]['sha'] = 'e'*40
        self.assertEqual(self.verify()['head_sha'], H)

    def test_case_rename_with_same_coverage_count_uses_normal_review(self):
        self.f.policy['suites']['qr']['cases'][1] = 'unrelated'
        self.assertEqual(self.verify()['head_sha'], H)

    def test_case_policy_can_change_through_normal_review(self):
        self.f.policy['suites']['qr']['cases'].pop()
        self.assertEqual(self.verify()['head_sha'], H)

    def test_missing_candidate_source_still_fails(self):
        self.f.tree = [row for row in self.f.tree if row['path'] != 'tests/scan.py']
        with self.assertRaises(ValueError): self.verify()

    def test_missing_skipped_or_neutral_required_job_refuses(self):
        for state in ['missing', 'skipped', 'neutral', 'failure', 'cancelled']:
            with self.subTest(state=state):
                self.f = AnchorFixture()
                if state == 'missing': self.f.jobs.pop()
                else: self.f.jobs[-1]['conclusion'] = state
                with self.assertRaises(ValueError): self.verify()

    def test_green_other_workflow_or_old_base_is_not_this_pr(self):
        for mutation in ['workflow', 'sha', 'base', 'event']:
            with self.subTest(mutation=mutation):
                self.f = AnchorFixture()
                if mutation == 'workflow': self.f.run['path'] = '.github/workflows/fake.yml'
                elif mutation == 'sha': self.f.run['head_sha'] = 'd'*40
                elif mutation == 'base': self.f.run['pull_requests'][0]['base']['sha'] = 'e'*40
                else: self.f.run['event'] = 'workflow_dispatch'
                with self.assertRaises(ValueError): self.verify()

    def test_new_failed_run_overrides_old_green(self):
        self.f.runs.append({**copy.deepcopy(self.f.run), 'id': 11, 'run_number': 6, 'conclusion': 'failure'})
        with self.assertRaises(ValueError): self.verify()

    def test_head_change_during_verification_refuses(self):
        self.f.change_head_after = True
        with self.assertRaises(ValueError): self.verify()

    def test_truncated_tree_or_missing_bootstrap_never_auto_approves(self):
        self.f.truncated = True
        with self.assertRaises(ValueError): self.verify()
        self.f = AnchorFixture(); self.f.bootstrap = True
        with self.assertRaises(ValueError): self.verify()


if __name__ == '__main__': unittest.main()
