"""WMS-652/517 explicit follow-up workflow contracts before command changes."""
import copy
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE_BINDING = ROOT / 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json'
WMS686_RECEIPT = ROOT / 'scripts/ci/tests/fixtures/wms686_raw_receipt_contract.json'
PRODUCT_SCOPE_PREFIX = 'python scripts/ci/product_scope.py --root . --trusted-ref '
WMS666_PREVIOUS_PRODUCT_SOURCE = '8ba63eadd9a4ce65d92f31c18a7276e049548eac'
WMS666_FINAL_PRODUCT_SOURCE = '739a63343fc38d2a3441d9b613b4652c7f0380e0'
WMS666_PREVIOUS_ACCEPTANCE_RECORD = 'c2cbd700fbf7f03fb00465b27ee8214428f9386e'
WMS652_PREVIOUS_ACCEPTED_SOURCES = (
    'd61805978b3e7878d1056c99b4e6e0823edf49a5',
    'ef154664e365644f4ba002c6e8affc5607fae725',
    '98978e667bbc305cc08a9b541016fef06686388e',
    '10c018092ab6f76928a54115eb824a64adc637be',
    'b2a03ec118f9b4a184edfc4c2973ff92e044fd6c',
    '7dbce79566246f7467bf1b7c84efa8cbe8f1cd9b',
    'd420f8db1e7d69212ad2ea4529a02044689363b0',
    WMS666_PREVIOUS_PRODUCT_SOURCE,
)


class ReleaseCommandContracts(unittest.TestCase):
    def guard_section(self, raw):
        return raw.split('\n  guards:\n', 1)[1].split('\n  printer-windows:', 1)[0]

    def source_binding(self):
        return json.loads(SOURCE_BINDING.read_text())

    def wms686_receipt(self):
        return json.loads(WMS686_RECEIPT.read_text())

    def trusted_reference(self, guard):
        matches = re.findall(re.escape(PRODUCT_SCOPE_PREFIX) + r'([^\s]+)', guard)
        self.assertEqual(len(matches), 1, 'guard must contain exactly one product-scope command')
        return matches[0]

    def assert_binding_is_independently_reviewed(self, guard, binding):
        trusted_ref = self.trusted_reference(guard)
        self.assertRegex(trusted_ref, r'^[0-9a-f]{40}$')
        self.assertIn(trusted_ref, binding['accepted_reviewed_sources'])
        self.assertNotIn(trusted_ref, binding['self_selecting_references'])
        self.assertNotEqual(trusted_ref, binding['unreviewed_candidate_source'])
        self.assertEqual(trusted_ref, self.active_reviewed_source(binding))
        return trusted_ref

    def active_reviewed_source(self, binding):
        if binding['status'] == 'pending-final-independent-freeze':
            self.assertIsNone(binding['final_reviewed_source'])
            self.assertEqual(binding['accepted_reviewed_sources'], [binding['current_reviewed_source']])
            return binding['current_reviewed_source']
        self.assertEqual(binding['status'], 'independently-accepted-final-freeze')
        final = binding['final_reviewed_source']
        self.assertRegex(final, r'^[0-9a-f]{40}$')
        self.assertIn(final, binding['accepted_reviewed_sources'])
        self.assertEqual(binding['frozen_source'], final)
        self.assertRegex(binding['independent_acceptance_record'], r'^[0-9a-f]{40}$')
        self.assertNotEqual(binding['independent_acceptance_record'], final)
        return final

    def assert_c71_exact_final_product_binding(self, guard, binding):
        self.assertEqual(binding['status'], 'independently-accepted-final-freeze')
        accepted = binding['accepted_reviewed_sources']
        self.assertEqual(accepted, [*WMS652_PREVIOUS_ACCEPTED_SOURCES,
                                    WMS666_FINAL_PRODUCT_SOURCE],
                         'the upgrade must append 739 without rewriting or extending the reviewed history')
        self.assertEqual(binding['final_reviewed_source'], WMS666_FINAL_PRODUCT_SOURCE)
        self.assertEqual(binding['frozen_source'], WMS666_FINAL_PRODUCT_SOURCE)
        trusted_ref = self.trusted_reference(guard)
        self.assertEqual(trusted_ref, WMS666_FINAL_PRODUCT_SOURCE)
        self.assertNotIn(trusted_ref, binding['self_selecting_references'])
        self.assertNotEqual(trusted_ref, binding['unreviewed_candidate_source'])
        return trusted_ref

    def assert_c71_saved_independent_acceptance_record(self, binding):
        record = binding.get('independent_acceptance_record')
        self.assertRegex(record or '', r'^[0-9a-f]{40}$')
        self.assertNotEqual(record, WMS666_FINAL_PRODUCT_SOURCE)
        self.assertNotEqual(record, WMS666_PREVIOUS_ACCEPTANCE_RECORD,
                            'the 8ba acceptance record cannot authorize the 739 transition')
        resolved = subprocess.run(
            ['git', '-C', str(ROOT), 'cat-file', '-e', record + '^{commit}'],
            capture_output=True, text=True, check=False)
        self.assertEqual(resolved.returncode, 0,
                         'the independent acceptance record must be a saved Git commit')

    def test_c71_final_binding_uses_exact_739_and_a_new_saved_acceptance_record(self):
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        binding = self.source_binding()
        self.assertEqual(self.assert_c71_exact_final_product_binding(guard, binding),
                         WMS666_FINAL_PRODUCT_SOURCE)
        self.assert_c71_saved_independent_acceptance_record(binding)

    def test_c71_final_binding_rejects_mismatch_self_selecting_and_unreviewed_sources(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guard = self.guard_section(raw)
        current = self.trusted_reference(guard)
        final_guard = guard.replace(PRODUCT_SCOPE_PREFIX + current,
                                    PRODUCT_SCOPE_PREFIX + WMS666_FINAL_PRODUCT_SOURCE)
        accepted = copy.deepcopy(self.source_binding())
        accepted['accepted_reviewed_sources'] = [*WMS652_PREVIOUS_ACCEPTED_SOURCES,
                                                  WMS666_FINAL_PRODUCT_SOURCE]
        accepted['final_reviewed_source'] = WMS666_FINAL_PRODUCT_SOURCE
        accepted['frozen_source'] = WMS666_FINAL_PRODUCT_SOURCE
        self.assertEqual(self.assert_c71_exact_final_product_binding(final_guard, accepted),
                         WMS666_FINAL_PRODUCT_SOURCE)

        previous_guard = final_guard.replace(PRODUCT_SCOPE_PREFIX + WMS666_FINAL_PRODUCT_SOURCE,
                                             PRODUCT_SCOPE_PREFIX + WMS666_PREVIOUS_PRODUCT_SOURCE)
        with self.subTest(rejected='previous-source-mismatch'):
            with self.assertRaises(AssertionError):
                self.assert_c71_exact_final_product_binding(previous_guard, accepted)

        mismatched = copy.deepcopy(accepted)
        mismatched['frozen_source'] = WMS666_PREVIOUS_PRODUCT_SOURCE
        with self.subTest(rejected='final-frozen-mismatch'):
            with self.assertRaises(AssertionError):
                self.assert_c71_exact_final_product_binding(final_guard, mismatched)

        neighboring = copy.deepcopy(accepted)
        neighboring['accepted_reviewed_sources'].append('7' * 40)
        with self.subTest(rejected='neighboring-unreviewed-source'):
            with self.assertRaises(AssertionError):
                self.assert_c71_exact_final_product_binding(final_guard, neighboring)

        for rejected in ['HEAD', '${GITHUB_SHA}', accepted['unreviewed_candidate_source']]:
            candidate_guard = final_guard.replace(
                PRODUCT_SCOPE_PREFIX + WMS666_FINAL_PRODUCT_SOURCE,
                PRODUCT_SCOPE_PREFIX + rejected)
            candidate_binding = copy.deepcopy(accepted)
            candidate_binding['final_reviewed_source'] = rejected
            candidate_binding['frozen_source'] = rejected
            with self.subTest(rejected=rejected):
                with self.assertRaises(AssertionError):
                    self.assert_c71_exact_final_product_binding(candidate_guard, candidate_binding)

    def test_c71_final_binding_requires_a_new_saved_independent_acceptance_record(self):
        binding = self.source_binding()
        self.assert_c71_saved_independent_acceptance_record(binding)
        for rejected in [None, WMS666_FINAL_PRODUCT_SOURCE,
                         WMS666_PREVIOUS_ACCEPTANCE_RECORD, 'f' * 40]:
            candidate = copy.deepcopy(binding)
            candidate['independent_acceptance_record'] = rejected
            with self.subTest(rejected=rejected):
                with self.assertRaises(AssertionError):
                    self.assert_c71_saved_independent_acceptance_record(candidate)

    def assert_wms686_raw_receipts(self, job, proof, receipt):
        self.assertEqual(receipt['test_count'], 11)
        command = f"node --test --test-reporter=tap {receipt['model_test']} > \"{receipt['tap_report']}\""
        compact_job = ' '.join(job.split())
        self.assertIn(command, compact_job)
        self.assertNotIn('--test-name-pattern', job)
        self.assertIn(f"name: {receipt['artifact']}", job)
        self.assertIn(receipt['tap_report'].replace('$RUNNER_TEMP', '${{ runner.temp }}'), job)
        self.assertIn('if-no-files-found: error', job)
        self.assertRegex(proof, rf'needs: \[[^\]]*\b{receipt["required_job"]}\b[^\]]*\]')
        artifact_name = f"name: {receipt['artifact']}"
        self.assertIn(artifact_name, proof)
        download = proof.split(artifact_name, 1)[1].split('- uses:', 1)[0]
        self.assertIn(f"path: {receipt['proof_download_path']}", download)

    def test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guard = self.guard_section(raw)
        binding = self.source_binding()
        expected = self.active_reviewed_source(binding)
        self.assertIn(PRODUCT_SCOPE_PREFIX + expected, guard)
        self.assertEqual(self.assert_binding_is_independently_reviewed(guard, binding), expected)
        self.assertIn('pytest -q scripts/ci/tests/test_product_scope.py --junitxml=', guard)

    def test_source_binding_keeps_one_active_exact_reference_during_or_after_freeze(self):
        binding = self.source_binding()
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        self.assertEqual(self.assert_binding_is_independently_reviewed(guard, binding),
                         self.active_reviewed_source(binding))

    def test_controlled_accepted_final_freeze_accepts_only_its_exact_reference(self):
        binding = self.source_binding()['controlled_accepted_final_binding']
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        current = self.trusted_reference(guard)
        final_guard = guard.replace(PRODUCT_SCOPE_PREFIX + current,
                                    PRODUCT_SCOPE_PREFIX + binding['final_reviewed_source'])
        self.assertEqual(self.assert_binding_is_independently_reviewed(final_guard, binding),
                         binding['final_reviewed_source'])
        with self.subTest(rejected='previous-source-mismatch'):
            with self.assertRaises(AssertionError):
                self.assert_binding_is_independently_reviewed(guard, binding)
        for rejected in [*binding['self_selecting_references'], binding['unreviewed_candidate_source']]:
            with self.subTest(rejected=rejected):
                candidate_guard = final_guard.replace(PRODUCT_SCOPE_PREFIX + binding['final_reviewed_source'],
                                                PRODUCT_SCOPE_PREFIX + rejected)
                with self.assertRaises(AssertionError):
                    self.assert_binding_is_independently_reviewed(candidate_guard, binding)

    def test_wms686_raw_receipt_contract_rejects_missing_tap_upload_download_or_required_job(self):
        receipt = self.wms686_receipt()
        job = f'''\
  wms686-mockup:
    steps:
      - run: node --test --test-reporter=tap {receipt['model_test']} > "{receipt['tap_report']}"
      - uses: actions/upload-artifact@v4
        with:
          name: {receipt['artifact']}
          path: ${{{{ runner.temp }}}}/wms686-model.tap
          if-no-files-found: error
'''
        proof = f'''\
  process-proof:
    needs: [baseline, backend, wms686-mockup]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: {receipt['artifact']}
          path: {receipt['proof_download_path']}
'''
        self.assert_wms686_raw_receipts(job, proof, receipt)
        mutations = {
            'tap-reporter': job.replace('--test-reporter=tap ', ''),
            'tap-file': job.replace(receipt['tap_report'], '$RUNNER_TEMP/not-wms686-model.tap'),
            'upload': job.replace(f"name: {receipt['artifact']}", 'name: another-artifact'),
            'download': proof.replace(f"name: {receipt['artifact']}", 'name: another-artifact'),
            'required-job': proof.replace(', wms686-mockup', ''),
        }
        for reason, (candidate_job, candidate_proof) in {
            'tap-reporter': (mutations['tap-reporter'], proof),
            'tap-file': (mutations['tap-file'], proof),
            'upload': (mutations['upload'], proof),
            'download': (job, mutations['download']),
            'required-job': (job, mutations['required-job']),
        }.items():
            with self.subTest(reason=reason):
                with self.assertRaises(AssertionError):
                    self.assert_wms686_raw_receipts(candidate_job, candidate_proof, receipt)

    def test_actual_workflow_requires_wms686_raw_tap_receipt_and_exact_attempt_artifact(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        receipt = self.wms686_receipt()
        if '\n  wms686-mockup:\n' not in raw:
            self.fail('WMS-686 mandatory model-test producer is absent from the actual CI workflow')
        job = raw.split('\n  wms686-mockup:\n', 1)[1].split('\n  guards:', 1)[0]
        proof = raw.split('\n  process-proof:\n', 1)[1]
        self.assert_wms686_raw_receipts(job, proof, receipt)

    def test_existing_517_pg_run_produces_report_without_duplicate_run(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        command = 'pytest -n 0 -m postgresql_concurrency tests/test_withdrawal_ledger.py tests/test_wb_order_price_snapshot.py tests/test_withdrawal_readiness.py'
        self.assertEqual(raw.count(command), 1)
        self.assertIn(command + ' --junitxml="$RUNNER_TEMP/release-postgres/517-withdrawal.xml"', raw)

    def test_all_three_mac_test_files_run_after_npm_ci_and_tap_is_in_frontend_artifact(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        front = raw.split('\n  frontend-build:\n', 1)[1].split('\n  guards:', 1)[0]
        self.assertLess(front.index('run: npm ci'), front.index('node --test --test-reporter=tap'))
        for name in ['wms517-mac-dom.test.cjs', 'wms517-mac-launcher.test.cjs', 'wms517-sold-kiz-filter.test.cjs']:
            self.assertIn('scripts/ops/tests/'+name, front)
        self.assertIn('> "$RUNNER_TEMP/wms517-mac.tap"', front)
        artifact = front.split('name: frontend-executed-contracts-', 1)[1]
        self.assertIn('${{ runner.temp }}/frontend-all.json', artifact)
        self.assertIn('${{ runner.temp }}/wms517-mac.tap', artifact)
        proof = raw.split('\n  process-proof:\n', 1)[1]
        self.assertIn('name: frontend-executed-contracts-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}', proof)


if __name__ == '__main__':
    unittest.main()
