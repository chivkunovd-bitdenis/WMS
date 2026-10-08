"""WMS-652/517 explicit follow-up workflow contracts before command changes."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE_BINDING = ROOT / 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json'
WMS686_RECEIPT = ROOT / 'scripts/ci/tests/fixtures/wms686_raw_receipt_contract.json'
PRODUCT_SCOPE_PREFIX = 'python scripts/ci/product_scope.py --root . --trusted-ref '


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
        self.assertEqual(trusted_ref, binding['reviewed_source'])
        self.assertNotIn(trusted_ref, binding['self_selecting_references'])
        self.assertNotEqual(trusted_ref, binding['unreviewed_candidate_source'])
        return trusted_ref

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

    def test_actual_candidate_product_scope_uses_independently_reviewed_source(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guard = self.guard_section(raw)
        binding = self.source_binding()
        expected = binding['reviewed_source']
        self.assertIn(PRODUCT_SCOPE_PREFIX + expected, guard)
        self.assertEqual(self.assert_binding_is_independently_reviewed(guard, binding), expected)
        self.assertIn('pytest -q scripts/ci/tests/test_product_scope.py --junitxml=', guard)

    def test_source_binding_accepts_only_the_exact_reviewed_reference(self):
        binding = self.source_binding()
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        self.assertEqual(self.assert_binding_is_independently_reviewed(guard, binding),
                         binding['reviewed_source'])
        for rejected in [binding['previous_source'], *binding['self_selecting_references'],
                         binding['unreviewed_candidate_source']]:
            candidate_guard = guard.replace(PRODUCT_SCOPE_PREFIX + binding['reviewed_source'],
                                            PRODUCT_SCOPE_PREFIX + rejected)
            with self.subTest(rejected=rejected), self.assertRaises(AssertionError):
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
