"""WMS-652: execution evidence must authorize the exact run before any action."""
import copy
import hashlib
import importlib
import io
import json
import unittest
import zipfile

from scripts.ci.tests.test_verify_ci import Fixture, REPO, SHA
from scripts.ci.verify_ci import GateError


class EvidenceFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.jobs.append(dict(id=80, name='process-proof', head_sha=SHA, run_id=10,
                              status='completed', conclusion='success'))
        self.policy = {'version': 1, 'files': {}, 'suites': {'packing': {
            'report': 'packing.xml', 'format': 'junit', 'exact': True,
            'cases': ['tests.scan::QR', 'tests.scan::nextQR']}}}
        self.policy_bytes = json.dumps(self.policy, sort_keys=True).encode()
        self.metadata = dict(version=1, sha=SHA, head_sha=SHA, base_sha='c'*40,
                             run_id=10, run_attempt=1,
                             policy_sha256=hashlib.sha256(self.policy_bytes).hexdigest())
        self.xml = (b'<testsuite><testcase classname="tests.scan" name="QR"/>'
                    b'<testcase classname="tests.scan" name="nextQR"/></testsuite>')
        self.artifacts = [dict(id=90, name=f'process-proof-{SHA}-10-1', expired=False,
            workflow_run={'id': 10, 'head_sha': SHA}, size_in_bytes=2000)]
        self.actions = []

    def get(self, path):
        if '/artifacts?' in path:
            self.paths.append(path)
            return copy.deepcopy({'total_count': len(self.artifacts), 'artifacts': self.artifacts})
        return super().get(path)

    def archive(self, _path):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('execution.json', json.dumps(self.metadata))
            archive.writestr('packing.xml', self.xml)
        return stream.getvalue()


class ProcessDeployGateTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.verify_process_ci')
        self.f = EvidenceFixture()

    def authorize_then_action(self):
        result = self.m.verify_execution(self.f.get, self.f.archive, REPO, SHA, self.f.policy_bytes)
        self.f.actions.append(('deploy', result['sha']))
        return result

    def reject(self):
        with self.assertRaises(GateError):
            self.authorize_then_action()
        self.assertEqual(self.f.actions, [])

    def test_exact_named_evidence_then_one_action(self):
        self.authorize_then_action()
        self.assertEqual(self.f.actions, [('deploy', SHA)])
        self.assertTrue(any('/runs/10/artifacts?' in path for path in self.f.paths))

    def test_green_jobs_without_evidence_never_deploy(self):
        self.f.artifacts = []
        self.reject()

    def test_skipped_required_case_or_same_count_replacement_never_deploy(self):
        for xml in [self.f.xml.replace(b'name="QR"/>', b'name="QR"><skipped/></testcase>'),
                    self.f.xml.replace(b'name="nextQR"', b'name="unrelated"'),
                    b'<testsuite/>', b'not XML']:
            with self.subTest(xml=xml):
                self.f.xml = xml
                self.reject()

    def test_wrong_sha_attempt_policy_or_run_never_deploy(self):
        for key, value in [('sha', 'b'*40), ('head_sha', 'b'*40), ('run_id', 11),
                           ('run_attempt', 2), ('policy_sha256', '0'*64)]:
            with self.subTest(key=key):
                self.f = EvidenceFixture()
                self.f.metadata[key] = value
                self.reject()

    def test_artifact_api_identity_not_self_declared_metadata(self):
        for mutation in ['sha', 'run', 'expired', 'duplicate', 'attempt', 'oversize']:
            with self.subTest(mutation=mutation):
                self.f = EvidenceFixture()
                artifact = self.f.artifacts[0]
                if mutation == 'sha':
                    artifact['workflow_run']['head_sha'] = 'b'*40
                elif mutation == 'run':
                    artifact['workflow_run']['id'] = 11
                elif mutation == 'expired':
                    artifact['expired'] = True
                elif mutation == 'duplicate':
                    self.f.artifacts.append({**copy.deepcopy(artifact), 'id': 91})
                elif mutation == 'attempt':
                    artifact['name'] = f'process-proof-{SHA}-10-2'
                else:
                    artifact['size_in_bytes'] = 10**10
                self.reject()

    def test_missing_failed_skipped_or_pending_proof_job_never_deploy(self):
        for state in ['missing', 'failure', 'skipped', 'cancelled', 'queued']:
            with self.subTest(state=state):
                self.f = EvidenceFixture()
                if state == 'missing':
                    self.f.jobs.pop()
                elif state == 'queued':
                    self.f.jobs[-1]['status'] = state
                else:
                    self.f.jobs[-1]['conclusion'] = state
                self.reject()

    def test_inaccessible_archive_never_deploy(self):
        def unavailable(_):
            raise OSError('unavailable')
        self.f.archive = unavailable
        self.reject()

    def test_archive_duplicate_members_and_traversal_refuse(self):
        original = self.f.archive
        for name in ['../escape', '/absolute', 'packing.xml']:
            with self.subTest(name=name):
                def broken(path):
                    stream = io.BytesIO(original(path))
                    with zipfile.ZipFile(stream, 'a') as archive:
                        archive.writestr(name, 'bad')
                    return stream.getvalue()
                self.f.archive = broken
                self.reject()

    def test_new_attempt_after_download_invalidates_old_receipt(self):
        original = self.f.archive
        def rerun(path):
            result = original(path)
            self.f.run['run_attempt'] = 2
            return result
        self.f.archive = rerun
        self.reject()


if __name__ == '__main__':
    unittest.main()
