"""WMS-652 strict anchor extension, frozen before artifact implementation."""
import copy
import hashlib
import importlib
import io
import json
import unittest
import zipfile

from scripts.ci.tests.test_trusted_process_check import REPO, AnchorFixture, B, H, M


class ArtifactFixture(AnchorFixture):
    def __init__(self):
        super().__init__()
        self.metadata = {'version': 1, 'sha': M, 'head_sha': H, 'base_sha': B, 'run_id': 10,
                         'run_attempt': 1, 'policy_sha256': self.digest()}
        self.artifacts = [{'id': 90, 'name': f'process-proof-{M}-10-1', 'expired': False,
                           'size_in_bytes': 2000, 'workflow_run': {'id': 10, 'head_sha': H}}]
        self.entries = [('execution.json', None)]
        self.advance_attempt = False
        self.run_reads = 0

    def digest(self):
        return hashlib.sha256(json.dumps(self.policy).encode()).hexdigest()

    def get(self, path):
        if '/artifacts?' in path:
            self.paths.append(path)
            return copy.deepcopy({'total_count': len(self.artifacts), 'artifacts': self.artifacts})
        if '/workflows/6/runs' in path:
            self.run_reads += 1
            if self.advance_attempt and self.run_reads > 1:
                self.run['run_attempt'] = 2
        return super().get(path)

    def download(self, path):
        self.paths.append(path)
        if path != f'repos/{REPO}/actions/artifacts/90/zip':
            raise AssertionError(path)
        result = io.BytesIO()
        with zipfile.ZipFile(result, 'w') as archive:
            for name, raw in self.entries:
                archive.writestr(name, json.dumps(self.metadata) if raw is None else raw)
        return result.getvalue()


class TrustedArtifactTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.trusted_process_check')
        self.f = ArtifactFixture()

    def verify(self):
        return self.m.verify_pr(self.f.get, REPO, 7, download=self.f.download)

    def reject(self):
        with self.assertRaises(ValueError):
            self.verify()

    def test_exact_merge_head_base_attempt_policy_proof_accepts(self):
        result = self.verify()
        self.assertEqual((result['head_sha'], result['base_sha'], result['merge_sha']), (H, B, M))
        self.assertEqual(result['artifact_id'], 90)
        self.assertIn(f'repos/{REPO}/actions/artifacts/90/zip', self.f.paths)

    def test_green_jobs_without_current_attempt_proof_refuses(self):
        self.f.artifacts = []
        self.reject()

    def test_wrong_tested_merge_head_base_attempt_run_policy_refuses(self):
        for key, value in [('sha', 'e'*40), ('head_sha', 'e'*40), ('base_sha', 'e'*40),
                           ('run_id', 11), ('run_attempt', 2), ('policy_sha256', '0'*64)]:
            with self.subTest(key=key):
                self.f = ArtifactFixture()
                self.f.metadata[key] = value
                self.reject()

    def test_missing_expired_duplicate_foreign_or_old_attempt_artifact_refuses(self):
        for mutation in ['missing', 'expired', 'duplicate', 'run', 'head', 'attempt', 'oversize']:
            with self.subTest(mutation=mutation):
                self.f = ArtifactFixture()
                row = self.f.artifacts[0]
                if mutation == 'missing': self.f.artifacts = []
                elif mutation == 'expired': row['expired'] = True
                elif mutation == 'duplicate': self.f.artifacts.append({**row, 'id': 91})
                elif mutation == 'run': row['workflow_run']['id'] = 11
                elif mutation == 'head': row['workflow_run']['head_sha'] = 'e'*40
                elif mutation == 'attempt': row['name'] = f'process-proof-{M}-10-2'
                else: row['size_in_bytes'] = 10**10
                self.reject()

    def test_zip_duplicate_traversal_symlink_missing_or_malformed_metadata_refuses(self):
        for entries in [[('execution.json', None), ('execution.json', None)],
                        [('../execution.json', None)], [('other.json', None)],
                        [('execution.json', 'not json')], [('execution.json', '[]')]]:
            with self.subTest(entries=entries):
                self.f.entries = entries
                self.reject()
        def symlink(_):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                info = zipfile.ZipInfo('execution.json')
                info.external_attr = 0o120777 << 16
                archive.writestr(info, json.dumps(self.f.metadata))
            return stream.getvalue()
        self.f.download = symlink
        self.reject()

    def test_latest_attempt_change_during_verification_refuses(self):
        self.f.advance_attempt = True
        self.reject()

    def test_tree_missing_changed_mode_symlink_or_duplicates_refuse(self):
        for mutation in ['missing', 'mode', 'symlink', 'type', 'duplicate']:
            with self.subTest(mutation=mutation):
                self.f = ArtifactFixture()
                if mutation == 'missing': self.f.tree.pop()
                elif mutation == 'mode': self.f.tree[-1]['mode'] = '100755'
                elif mutation == 'symlink': self.f.tree[-1]['mode'] = '120000'
                elif mutation == 'type': self.f.tree[-1]['type'] = 'commit'
                else: self.f.tree.append(copy.deepcopy(self.f.tree[-1]))
                self.reject()

    def test_policy_cannot_remove_suite_change_report_format_or_exact(self):
        for field, value in [('report', 'different.json'), ('format', 'junit'), ('exact', False)]:
            with self.subTest(field=field):
                self.f = ArtifactFixture()
                self.f.policy['suites']['qr'][field] = value
                self.reject()
        self.f = ArtifactFixture()
        self.f.policy['suites'].pop('qr')
        self.reject()

    def test_closed_wrong_target_or_merge_sha_changed_pr_refuses(self):
        for field in ['state', 'target', 'merge']:
            with self.subTest(field=field):
                self.f = ArtifactFixture()
                if field == 'state': self.f.pr['state'] = 'closed'
                elif field == 'target': self.f.pr['base']['ref'] = 'main'
                else: self.f.pr['merge_commit_sha'] = None
                self.reject()


if __name__ == '__main__':
    unittest.main()
