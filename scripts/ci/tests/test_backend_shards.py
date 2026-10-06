"""WMS-652 two-way full backend CI: frozen before shard implementation."""
import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COLLECTION = ROOT / 'docs/evidence/WMS-652/ci-two-shards-20261006/backend-collection.json'
IDENTITY = {'sha': 'a'*40, 'run_id': 100, 'run_attempt': 2}
IDS = ['tests/test_a.py::test_pass', 'tests/test_b.py::test_skip',
       'tests/test_c.py::test_fail', 'tests/test_d.py::test_error']


def report(path, ids, outcomes=None):
    outcomes = outcomes or {}
    root = ET.Element('testsuites')
    suite = ET.SubElement(root, 'testsuite', name='pytest', tests=str(len(ids)))
    for node in ids:
        file, name = node.split('::', 1)
        case = ET.SubElement(suite, 'testcase', classname=file[:-3].replace('/', '.'), name=name, time='0.5')
        properties = ET.SubElement(case, 'properties')
        ET.SubElement(properties, 'property', name='wms_nodeid', value=node)
        if node in outcomes:
            ET.SubElement(case, outcomes[node], message='synthetic '+outcomes[node]).text = 'original detail'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def fixture(folder, ids=IDS, outcomes=None):
    paths = []
    for index in range(2):
        path = Path(folder) / str(index)
        path.mkdir()
        selected = sorted(ids)[index::2]
        receipt = {**IDENTITY, 'version': 1, 'index': index, 'count': 2,
                   'collection': sorted(ids), 'selected': selected, 'exit_code': 0}
        (path / 'receipt.json').write_text(json.dumps(receipt))
        report(path / 'junit.xml', selected, outcomes)
        paths.append(path)
    return paths


class BackendShardContracts(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.backend_shards')

    def test_real_full_collection_partition_exact_union_once_and_balanced(self):
        ids = json.loads(COLLECTION.read_text())
        self.assertGreater(len(ids), 4000)
        left, right = [self.m.partition(ids, index) for index in range(2)]
        self.assertEqual(set(left) | set(right), set(ids))
        self.assertEqual(set(left) & set(right), set())
        self.assertEqual(len(left) + len(right), len(ids))
        self.assertLessEqual(abs(len(left)-len(right)), 1)
        self.assertEqual(self.m.partition(list(reversed(ids)), 0), left)

    def test_duplicate_empty_or_bad_shard_collection_refuses(self):
        for ids, index in [([], 0), ([IDS[0], IDS[0]], 0), (IDS, -1), (IDS, 2), (IDS, True)]:
            with self.subTest(ids=ids, index=index), self.assertRaises(ValueError):
                self.m.partition(ids, index)

    def test_exact_two_shards_merge_all_cases_and_receipt_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = fixture(folder)
            output = Path(folder) / 'backend-all.xml'
            result = self.m.merge(paths, output, IDENTITY, required=['tests.test_a::test_pass'])
            self.assertTrue(result['success'])
            cases = list(ET.parse(output).iter('testcase'))
            self.assertEqual(len(cases), len(IDS))
            self.assertEqual({c.find('properties/property').get('value') for c in cases}, set(IDS))
            self.assertEqual(result['tests'], len(IDS))

    def test_missing_duplicate_shard_wrong_index_collection_or_selection_refuses(self):
        for mutation in ['missing', 'duplicate-index', 'collection', 'selection', 'empty']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                paths = fixture(folder)
                if mutation == 'missing': paths.pop()
                else:
                    p = paths[1] / 'receipt.json'
                    receipt = json.loads(p.read_text())
                    if mutation == 'duplicate-index': receipt['index'] = 0
                    elif mutation == 'collection': receipt['collection'].pop()
                    elif mutation == 'selection': receipt['selected'] = receipt['collection']
                    else: receipt['selected'] = []
                    p.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    self.m.merge(paths, Path(folder)/'out.xml', IDENTITY)

    def test_wrong_sha_run_or_attempt_and_missing_metadata_refuse(self):
        for field, value in [('sha', 'b'*40), ('run_id', 101), ('run_attempt', 1), ('version', 2)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                paths = fixture(folder)
                p = paths[0] / 'receipt.json'
                receipt = json.loads(p.read_text())
                receipt[field] = value
                p.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError): self.m.merge(paths, Path(folder)/'out.xml', IDENTITY)

    def test_missing_duplicate_extra_or_unidentified_junit_case_refuses(self):
        for mutation in ['missing', 'duplicate', 'extra', 'no-nodeid']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                paths = fixture(folder)
                p = paths[0]/'junit.xml'
                tree = ET.parse(p)
                suite = tree.getroot().find('testsuite')
                case = suite.find('testcase')
                if mutation == 'missing': suite.remove(case)
                elif mutation == 'duplicate': suite.append(copy.deepcopy(case))
                elif mutation == 'extra':
                    extra = copy.deepcopy(case)
                    extra.find('properties/property').set('value', 'tests/test_extra.py::test_extra')
                    suite.append(extra)
                else: case.remove(case.find('properties'))
                tree.write(p)
                with self.assertRaises(ValueError): self.m.merge(paths, Path(folder)/'out.xml', IDENTITY)

    def test_required_skipped_case_never_counts_as_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = fixture(folder, outcomes={IDS[0]: 'skipped'})
            with self.assertRaises(ValueError):
                self.m.merge(paths, Path(folder)/'out.xml', IDENTITY, required=['tests.test_a::test_pass'])

    def test_merge_preserves_failure_error_skip_details_and_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = fixture(folder, outcomes={IDS[1]: 'skipped', IDS[2]: 'failure', IDS[3]: 'error'})
            output = Path(folder)/'out.xml'
            result = self.m.merge(paths, output, IDENTITY)
            self.assertFalse(result['success'])
            self.assertEqual([result[k] for k in ['tests', 'failures', 'errors', 'skipped']], [4, 1, 1, 1])
            for tag in ['failure', 'error', 'skipped']:
                self.assertEqual(next(ET.parse(output).iter(tag)).text, 'original detail')

    def test_nonzero_pytest_exit_never_reports_success_even_with_all_green_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = fixture(folder)
            p = paths[0]/'receipt.json'
            receipt = json.loads(p.read_text())
            receipt['exit_code'] = 1
            p.write_text(json.dumps(receipt))
            self.assertFalse(self.m.merge(paths, Path(folder)/'out.xml', IDENTITY)['success'])

    def test_actual_pytest_xdist_receipts_use_exact_full_collection_and_junit_nodeids(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'test_synthetic.py').write_text('import pytest\n@pytest.mark.parametrize("n", [0,1,2,3])\ndef test_case(n): assert n >= 0\n')
            environment = {**os.environ, 'GITHUB_SHA': IDENTITY['sha'],
                           'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_ACTIONS': 'false'}
            paths = []
            for index in range(2):
                output = root/str(index)
                run = subprocess.run([sys.executable, str(ROOT/'scripts/ci/backend_shards.py'),
                    'run', '--index', str(index), '--output', str(output), '--', '-n', '2', '-q', 'test_synthetic.py'],
                    cwd=root, env=environment, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
                paths.append(output)
            result = self.m.merge(paths, root/'merged.xml', IDENTITY)
            self.assertEqual(result['tests'], 4)
            self.assertTrue(result['success'])


class BackendWorkflowContracts(unittest.TestCase):
    def test_required_backend_aggregates_checks_and_both_shards_and_preserves_pg_steps(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        backend = raw.split('\n  backend:\n', 1)[1].split('\n  print-regressions:', 1)[0]
        self.assertIn('needs: [backend-checks, backend-shards]', backend)
        self.assertIn('if: always()', backend)
        self.assertIn('needs.backend-checks.result', backend)
        self.assertIn('needs.backend-shards.result', backend)
        self.assertIn('backend_shards.py merge', backend)
        self.assertIn('backend-executed-contracts-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}', backend)
        for command in ['run_release_postgres.sh', 'alembic downgrade 20260923_0517',
                        'test_wms662_batch_handoff_lock_order.py', 'test_wms662_batch_handoff_steady_state.py',
                        'ruff check .', 'mypy .']:
            self.assertIn(command, raw)
        self.assertIn('index: [0, 1]', raw)
        self.assertIn('fail-fast: false', raw)

    def test_frontend_runs_parallel_print_and_process_proof_requires_both(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        front = raw.split('\n  frontend-build:\n', 1)[1].split('\n  guards:', 1)[0]
        self.assertNotIn('needs: print-regressions', front)
        proof = raw.split('\n  process-proof:\n', 1)[1]
        self.assertIn('frontend-build, guards, print-regressions, printer-windows', proof)

    def test_guard_installs_pytest_before_discovery_and_uploads_real_product_scope_junit(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guard = raw.split('\n  guards:\n', 1)[1].split('\n  printer-windows:', 1)[0]
        self.assertLess(guard.index('pip install pytest'), guard.index('python -m unittest discover'))
        self.assertIn('pytest -q scripts/ci/tests/test_product_scope.py --junitxml=', guard)
        self.assertIn('product-scope.xml', guard)
        self.assertIn('actions/upload-artifact@v4', guard)
        proof = raw.split('\n  process-proof:\n', 1)[1]
        self.assertIn('guard-executed-contracts-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}', proof)


if __name__ == '__main__':
    unittest.main()
