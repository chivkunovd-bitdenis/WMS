"""WMS-652: exact execution and immutable source contract, before implementation.

All data is synthetic; no GitHub, printer, marketplace or production calls.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESS_POLICY = REPO_ROOT / 'guards/PROCESS_CONTRACTS.json'
WMS666_C13_TEST_FILE = 'frontend/src/screens/v2/wms666ChangeScope.test.ts'
WMS666_C13_CASES = (
    'src/screens/v2/wms666ChangeScope.test.ts::rejects migrations, backend entities, stock logic and guard registry changes',
    'src/screens/v2/wms666ChangeScope.test.ts::keeps the actual task diff inside the approved packing UI/test/document boundary',
    'src/screens/v2/wms666ChangeScope.test.ts::accepts exact task proofs and rejects adjacent proof and correction namespaces',
    'src/screens/v2/wms666ChangeScope.test.ts::reads advancing task history: foreign backend passes, new task backend or guards fail',
    'src/screens/v2/wms666ChangeScope.test.ts::checks task merge resolutions while ignoring an imported foreign backend tree',
    'src/screens/v2/wms666ChangeScope.test.ts::rejects a new task workflow edit and pending CI changes independently',
    'src/screens/v2/wms666ChangeScope.test.ts::accepts only reviewed recovery commit/path/blob triples and rejects adjacent paths',
    'src/screens/v2/wms666ChangeScope.test.ts::accepts only the exact immutable history checkout delta',
    'src/screens/v2/wms666ChangeScope.test.ts::fails an accepted history lookup if its immutable source is missing',
    'src/screens/v2/wms666ChangeScope.test.ts::accepts only exact doc-only historical commits and keeps their paths forbidden generally',
    'src/screens/v2/wms666ChangeScope.test.ts::records only the five exact RC7 service blob pairs and each commit full path list',
    'src/screens/v2/wms666ChangeScope.test.ts::rejects RC7 history when commit, path, blob, mode, or complete path list differs',
    'src/screens/v2/wms666ChangeScope.test.ts::accepts only the exact WMS-517 financial fixture correction history',
    'src/screens/v2/wms666ChangeScope.test.ts::rejects adjacent WMS-517 correction commits and mutated exact-history entries',
    'src/screens/v2/wms666ChangeScope.test.ts::rejects future WMS-517 path commits and dirty, staged, or untracked changes',
    'src/screens/v2/wms666ChangeScope.test.ts::fails closed when an exact RC7 source commit cannot be resolved',
    'src/screens/v2/wms666ChangeScope.test.ts::rejects future committed, dirty and staged edits of every historical document path',
    'src/screens/v2/wms666ChangeScope.test.ts::fails exact doc-history lookup when immutable objects are absent',
)
WMS652_C71_CASES = (
    'scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts::test_c71_final_binding_uses_exact_739_and_a_new_saved_acceptance_record',
    'scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts::test_c71_final_binding_rejects_mismatch_self_selecting_and_unreviewed_sources',
    'scripts.ci.tests.test_ci_release_additions.ReleaseCommandContracts::test_c71_final_binding_requires_a_new_saved_independent_acceptance_record',
    'scripts.ci.tests.test_process_contracts.ProcessContractTests::test_c71_all_wms666_c13_cases_are_protected_and_registered_without_suite_changes',
    'scripts.ci.tests.test_process_contracts.ProcessContractTests::test_c71_frontend_receipt_rejects_missing_skipped_or_misattributed_c13_cases',
)


def junit(rows):
    return ('<testsuites><testsuite>' + ''.join(
        f'<testcase classname="tests.test_pick" name="{name}">{body}</testcase>'
        for name, body in rows) + '</testsuite></testsuites>').encode()


class ProcessContractTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.process_contracts')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = {'version': 1, 'files': {}, 'suites': {
            'picking': {'report': 'picking.xml', 'format': 'junit', 'exact': True,
                        'cases': ['tests.test_pick::scan[EAN]', 'tests.test_pick::undo']}}}
        (self.root / 'picking.xml').write_bytes(junit([('scan[EAN]', ''), ('undo', '')]))

    def test_real_named_cases_green(self):
        result = self.m.verify_reports(self.policy, self.root)
        self.assertEqual(result, {'picking': self.policy['suites']['picking']['cases']})

    def test_same_count_other_case_cannot_replace_required_case(self):
        (self.root / 'picking.xml').write_bytes(junit([('scan[EAN]', ''), ('unrelated', '')]))
        with self.assertRaisesRegex(ValueError, 'undo'):
            self.m.verify_reports(self.policy, self.root)

    def test_duplicate_cannot_replace_missing_case(self):
        (self.root / 'picking.xml').write_bytes(junit([('scan[EAN]', ''), ('scan[EAN]', '')]))
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_every_nonpass_and_collection_error_refuse(self):
        for body in ['<skipped/>', '<failure/>', '<error/>']:
            with self.subTest(body=body):
                (self.root / 'picking.xml').write_bytes(junit([('scan[EAN]', body), ('undo', '')]))
                with self.assertRaises(ValueError):
                    self.m.verify_reports(self.policy, self.root)
        (self.root / 'picking.xml').write_bytes(junit([('scan[EAN]', ''), ('undo', '')])
            .replace(b'</testsuite>', b'<testcase name="collection"><error/></testcase></testsuite>'))
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_unavailable_empty_malformed_or_symlink_report_refuses(self):
        path = self.root / 'picking.xml'
        for content in [b'', b'not xml', b'<testsuites/>']:
            path.write_bytes(content)
            with self.assertRaises((ValueError, OSError)):
                self.m.verify_reports(self.policy, self.root)
        path.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.m.verify_reports(self.policy, self.root)
        outside = self.root / 'other.xml'
        outside.write_bytes(junit([('scan[EAN]', ''), ('undo', '')]))
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_subset_allows_unrelated_skip_but_never_protected_skip(self):
        self.policy['suites']['picking']['exact'] = False
        (self.root / 'picking.xml').write_bytes(junit([
            ('scan[EAN]', ''), ('undo', ''), ('external_manual_only', '<skipped/>')]))
        self.m.verify_reports(self.policy, self.root)
        (self.root / 'picking.xml').write_bytes(junit([
            ('scan[EAN]', ''), ('undo', '<skipped/>'), ('external_manual_only', '')]))
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_vitest_requires_file_and_full_parameterized_name_not_summary(self):
        self.policy['suites'] = {'scan': {'report': 'scan.json', 'format': 'vitest',
            'exact': True, 'cases': ['src/guards/scan.test.ts::QR [both flags]']}}
        report = {'success': True, 'testResults': [{
            'name': '/runner/w/WMS/frontend/src/guards/scan.test.ts',
            'assertionResults': [{'fullName': 'QR [both flags]', 'status': 'passed'}]}]}
        path = self.root / 'scan.json'
        path.write_text(json.dumps(report))
        self.m.verify_reports(self.policy, self.root)
        for field, value in [('status', 'pending'), ('status', 'todo'),
                             ('fullName', 'unrelated'), ('status', 'failed')]:
            broken = copy.deepcopy(report)
            broken['testResults'][0]['assertionResults'][0][field] = value
            path.write_text(json.dumps(broken))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.m.verify_reports(self.policy, self.root)
        report['testResults'][0]['name'] = '/runner/frontend/src/other/scan.test.ts'
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_c71_all_wms666_c13_cases_are_protected_and_registered_without_suite_changes(self):
        manifest = json.loads(PROCESS_POLICY.read_text())
        source_path = REPO_ROOT / WMS666_C13_TEST_FILE
        source = source_path.read_bytes()
        actual_names = re.findall(r"^\s*it\('([^']+)'", source.decode(), re.MULTILINE)
        actual_cases = tuple('src/screens/v2/wms666ChangeScope.test.ts::' + name
                             for name in actual_names)
        self.assertEqual(actual_cases, WMS666_C13_CASES,
                         'the C13 file must retain the exact 18 frozen case names')

        self.assertIn(WMS666_C13_TEST_FILE, manifest['files'])
        self.assertEqual(manifest['files'][WMS666_C13_TEST_FILE],
                         hashlib.sha256(source).hexdigest())
        suite = manifest['suites']['frontend-fbs']
        self.assertEqual({key: suite[key] for key in ('report', 'format', 'exact')},
                         {'report': 'frontend-all.json', 'format': 'vitest', 'exact': False})
        self.assertEqual(len(suite['cases']), len(set(suite['cases'])))
        self.assertTrue(set(WMS666_C13_CASES).issubset(suite['cases']))
        self.assertEqual(len(manifest['files']), 283)
        self.assertEqual(len(manifest['suites']), 29)
        self.assertEqual(len(suite['cases']), 355)
        self.assertTrue(set(WMS652_C71_CASES).issubset(manifest['suites']['ci-shards']['cases']))
        self.assertEqual(sum(len(item['cases']) for item in manifest['suites'].values()), 1742)

    def test_c71_frontend_receipt_rejects_missing_skipped_or_misattributed_c13_cases(self):
        policy = {'version': 1, 'files': {}, 'suites': {
            'frontend-fbs': {'report': 'frontend-all.json', 'format': 'vitest',
                             'exact': False, 'cases': list(WMS666_C13_CASES)}}}
        test_results = [{'name': '/runner/work/WMS/frontend/' + WMS666_C13_TEST_FILE,
                         'assertionResults': [
                             {'fullName': case.split('::', 1)[1], 'status': 'passed'}
                             for case in WMS666_C13_CASES]}]
        report = {'success': True, 'testResults': test_results}
        report_path = self.root / 'frontend-all.json'
        report_path.write_text(json.dumps(report))
        self.assertEqual(self.m.verify_reports(policy, self.root),
                         {'frontend-fbs': list(WMS666_C13_CASES)})

        mutations = {}
        missing = copy.deepcopy(report)
        missing['testResults'][0]['assertionResults'].pop()
        mutations['missing-case'] = missing
        skipped = copy.deepcopy(report)
        skipped['testResults'][0]['assertionResults'][0]['status'] = 'pending'
        mutations['skipped-case'] = skipped
        wrong_case = copy.deepcopy(report)
        wrong_case['testResults'][0]['assertionResults'][0]['fullName'] = 'unrelated case'
        mutations['wrong-case'] = wrong_case
        wrong_file = copy.deepcopy(report)
        wrong_file['testResults'][0]['name'] = '/runner/work/WMS/frontend/src/screens/v2/other.test.ts'
        mutations['wrong-file'] = wrong_file
        for name, candidate in mutations.items():
            with self.subTest(mutation=name):
                report_path.write_text(json.dumps(candidate))
                with self.assertRaises(ValueError):
                    self.m.verify_reports(policy, self.root)

    def test_no_external_paths_or_empty_policy(self):
        for report in ['../picking.xml', '/tmp/picking.xml', 'a/../../picking.xml']:
            policy = copy.deepcopy(self.policy)
            policy['suites']['picking']['report'] = report
            with self.assertRaises(ValueError):
                self.m.verify_reports(policy, self.root)
        self.policy['suites'] = {}
        with self.assertRaises(ValueError):
            self.m.verify_reports(self.policy, self.root)

    def test_browser_report_is_exact_named_actual_sha_not_old_green(self):
        self.policy['suites'] = {'real-input': {'report': 'browser.json', 'format': 'browser-json',
            'exact': True, 'cases': ['QR[first]', 'QR[next]']}}
        original = {'sha': 'a'*40, 'status': 'PASS', 'cases': [
            {'id': 'QR[first]', 'status': 'PASS'}, {'id': 'QR[next]', 'status': 'PASS'}]}
        path = self.root / 'browser.json'
        path.write_text(json.dumps(original))
        self.m.verify_reports(self.policy, self.root, sha='a'*40)
        for mutation in ['old-sha', 'skip', 'missing', 'same-count-wrong-case', 'duplicate', 'failed-suite']:
            data = copy.deepcopy(original)
            if mutation == 'old-sha': data['sha'] = 'b'*40
            elif mutation == 'skip': data['cases'][0]['status'] = 'SKIP'
            elif mutation == 'missing': data['cases'].pop()
            elif mutation == 'same-count-wrong-case': data['cases'][0]['id'] = 'unrelated'
            elif mutation == 'duplicate': data['cases'][1] = data['cases'][0]
            else: data['status'] = 'FAIL'
            path.write_text(json.dumps(data))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.m.verify_reports(self.policy, self.root, sha='a'*40)

    def test_freeze_rejects_source_helper_runner_and_self_updated_hash(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        for path in ['tests/test_scan.py', 'tests/helpers.py', '.github/workflows/ci.yml']:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('original contract\n')
            self.policy['files'][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        policy_path = self.root / self.m.POLICY_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(self.policy))
        git('add', '.')
        git('commit', '-qm', 'fixture')
        base = git('rev-parse', 'HEAD').decode().strip()
        self.m.verify_integrity(self.root, base)
        for name in self.policy['files']:
            with self.subTest(path=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_text('assert True # weakened or launch disabled\n')
                changed = copy.deepcopy(self.policy)
                changed['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
                policy_path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'protected'):
                    self.m.verify_integrity(self.root, base)
                path.write_bytes(original)
                policy_path.write_text(json.dumps(self.policy))
        changed = copy.deepcopy(self.policy)
        changed['suites']['picking']['cases'].remove('tests.test_pick::undo')
        policy_path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.m.verify_integrity(self.root, base)


if __name__ == '__main__':
    unittest.main()
