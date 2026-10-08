"""WMS-652: exact execution and immutable source contract, before implementation.

All data is synthetic; no GitHub, printer, marketplace or production calls.
"""
import copy
import importlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


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

    def test_source_fixture_addition_and_rename_pass_without_external_pin(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        for path in ['tests/test_scan.py', 'tests/helpers.py']:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('original contract\n')
            self.policy['files'][path] = 'a' * 64
        policy_path = self.root / self.m.POLICY_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(self.policy))
        git('add', '.')
        git('commit', '-qm', 'fixture')
        base = git('rev-parse', 'HEAD').decode().strip()
        self.m.verify_integrity(self.root, base)
        (self.root / 'tests/test_scan.py').write_text('def test_scan(): assert True\n')
        (self.root / 'tests/helpers.py').rename(self.root / 'tests/fixtures.py')
        (self.root / 'tests/new_scan_test.py').write_text('def test_added(): assert True\n')
        self.m.verify_integrity(self.root, base)

    def test_renamed_case_with_same_coverage_count_passes_and_runs(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        source = self.root / 'tests/test_scan.py'
        source.parent.mkdir(parents=True)
        source.write_text('def test_scan(): assert True\n')
        policy_path = self.root / self.m.POLICY_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy['files']['tests/test_scan.py'] = 'a' * 64
        policy_path.write_text(json.dumps(self.policy))
        git('add', '.')
        git('commit', '-qm', 'fixture')
        base = git('rev-parse', 'HEAD').decode().strip()
        changed = copy.deepcopy(self.policy)
        changed['suites']['picking']['cases'][0] = 'tests.test_pick::scan[renamed]'
        source.rename(source.with_name('test_scan_renamed.py'))
        policy_path.write_text(json.dumps(changed))
        self.assertEqual(self.m.verify_integrity(self.root, base), changed)
        (self.root / 'picking.xml').write_bytes(junit([('scan[renamed]', ''), ('undo', '')]))
        self.m.verify_reports(changed, self.root)

    def test_removing_mandatory_case_is_still_rejected(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        policy_path = self.root / self.m.POLICY_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(self.policy))
        git('add', '.')
        git('commit', '-qm', 'fixture')
        base = git('rev-parse', 'HEAD').decode().strip()
        changed = copy.deepcopy(self.policy)
        changed['suites']['picking']['cases'].remove('tests.test_pick::undo')
        policy_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'case count decreased'):
            self.m.verify_integrity(self.root, base)


if __name__ == '__main__':
    unittest.main()
