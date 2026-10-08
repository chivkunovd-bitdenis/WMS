"""WMS-652/517 explicit follow-up workflow contracts before command changes."""
import json
import re
import unittest
from pathlib import Path

from scripts.ci.select_process_artifacts import PRODUCERS, SelectionError, select_artifacts

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
        artifact_name = f"name: ${{{{ steps.select.outputs.wms686_mockup }}}}"
        if artifact_name not in proof:
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
        self.assertIn('name: ${{ steps.select.outputs.frontend_build }}', proof)

    def test_nightly_controller_report_is_uploaded_and_required_by_manifest(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guards = raw.split('\n  guards:\n', 1)[1].split('\n  printer-windows:\n', 1)[0]
        self.assertIn('tools/support_agent/tests/test_night.py', guards)
        self.assertIn('--junitxml="$RUNNER_TEMP/night-controller.xml"', guards)
        self.assertIn('${{ runner.temp }}/night-controller.xml', guards)
        policy = json.loads((ROOT/'guards/PROCESS_CONTRACTS.json').read_text())
        suite = policy['suites']['night-controller']
        self.assertEqual(suite['report'], 'night-controller.xml')
        self.assertTrue(suite['exact'])
        self.assertTrue(suite['cases'])
        self.assertEqual(len(suite['cases']), len(set(suite['cases'])))
        self.assertTrue(all(case.startswith('tests.test_night::') for case in suite['cases']))

    def test_actual_workflow_selects_exact_attempt_artifacts_with_read_only_api(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        proof = raw.split('\n  process-proof:\n', 1)[1]
        self.assertIn('actions: read', proof)
        self.assertIn('scripts/ci/select_process_artifacts.py', proof)
        self.assertIn('name: ${{ steps.select.outputs.backend }}', proof)
        self.assertNotIn('name: backend-executed-contracts-${{ github.sha }}', proof)
        self.assertEqual(proof.count("steps.select.outcome == 'success'"), 7)
        for download in ['download-backend', 'download-frontend', 'download-windows',
                         'download-print', 'download-guards', 'download-wms686']:
            self.assertIn(f'steps.{download}.outcome == \'success\'', proof)

    def _partial_rerun_fixture(self):
        run_id, current_attempt = 777, 2
        tested_sha = 'a' * 40
        candidate_sha = 'b' * 40
        old = {'started_at': '2026-10-08T09:43:55Z', 'completed_at': '2026-10-08T09:44:28Z',
               'status': 'completed', 'conclusion': 'success'}
        recent = {'started_at': '2026-10-08T09:59:15Z', 'completed_at': '2026-10-08T10:09:20Z',
                  'status': 'completed', 'conclusion': 'success'}
        attempts = [[], []]
        artifacts = []
        for name, prefix in PRODUCERS.items():
            job1 = {**old, 'name': name, 'run_id': run_id, 'head_sha': candidate_sha,
                    'run_attempt': 1}
            job2 = {**(recent if name == 'print-regressions' else old), 'name': name,
                    'run_id': run_id, 'head_sha': candidate_sha, 'run_attempt': 2}
            attempts[0].append(job1)
            attempts[1].append(job2)
            selected_attempt = 2 if name == 'print-regressions' else 1
            executed = recent if selected_attempt == 2 else old
            artifacts.append({
                'name': f'{prefix}-{tested_sha}-{run_id}-{selected_attempt}',
                'expired': False,
                'created_at': executed['completed_at'],
                'workflow_run': {'id': run_id, 'head_sha': candidate_sha},
            })
        return dict(run_id=run_id, current_attempt=current_attempt, tested_sha=tested_sha,
                    candidate_sha=candidate_sha, run={'id': run_id, 'head_sha': candidate_sha},
                    job_attempts=attempts, artifacts=artifacts)

    def test_partial_rerun_selects_mixed_successful_attempts_from_same_run(self):
        fixture = self._partial_rerun_fixture()
        selected = select_artifacts(**fixture)
        self.assertTrue(selected['backend'].endswith('-777-1'))
        self.assertTrue(selected['print-regressions'].endswith('-777-2'))

    def test_partial_rerun_never_falls_back_when_repeated_job_report_is_missing(self):
        fixture = self._partial_rerun_fixture()
        fixture['artifacts'] = [a for a in fixture['artifacts']
                                if not a['name'].startswith('release-print-')]
        with self.assertRaisesRegex(SelectionError, 'Missing or ambiguous report'):
            select_artifacts(**fixture)

    def test_partial_rerun_rejects_failed_skipped_or_cancelled_latest_job(self):
        for conclusion in ['failure', 'skipped', 'cancelled']:
            with self.subTest(conclusion=conclusion):
                fixture = self._partial_rerun_fixture()
                job = next(job for job in fixture['job_attempts'][1]
                           if job['name'] == 'print-regressions')
                job['conclusion'] = conclusion
                if conclusion != 'skipped':
                    job['status'] = 'completed'
                with self.assertRaisesRegex(SelectionError, 'did not succeed'):
                    select_artifacts(**fixture)

    def test_partial_rerun_rejects_cross_run_or_cross_sha_artifacts(self):
        for field, value in [('id', 778), ('head_sha', 'c' * 40)]:
            with self.subTest(field=field):
                fixture = self._partial_rerun_fixture()
                fixture['artifacts'][0]['workflow_run'][field] = value
                with self.assertRaisesRegex(SelectionError, 'does not belong'):
                    select_artifacts(**fixture)
        fixture = self._partial_rerun_fixture()
        fixture['run']['head_sha'] = 'c' * 40
        with self.assertRaisesRegex(SelectionError, 'identity mismatch'):
            select_artifacts(**fixture)

    def test_cancelled_attempt_without_runner_can_be_replaced_by_successful_retry(self):
        fixture = self._partial_rerun_fixture()
        jobs = fixture['job_attempts']
        for job in jobs[0]:
            job.update(started_at=None, completed_at=None, status='completed', conclusion='cancelled')
        for artifact in fixture['artifacts']:
            parts = artifact['name'].rsplit('-', 1)
            artifact['name'] = f'{parts[0]}-2'
            artifact['created_at'] = '2026-10-08T10:09:20Z'
        for job in jobs[1]:
            job.update(started_at='2026-10-08T09:59:15Z',
                       completed_at='2026-10-08T10:09:20Z')
        selected = select_artifacts(**fixture)
        self.assertTrue(all(value.endswith('-777-2') for value in selected.values()))

    def test_latest_job_identity_or_pending_status_refuses_report(self):
        for field, value in [('run_id', 778), ('head_sha', 'c' * 40), ('run_attempt', 1)]:
            with self.subTest(field=field):
                fixture = self._partial_rerun_fixture()
                fixture['job_attempts'][1][0][field] = value
                with self.assertRaisesRegex(SelectionError, 'job identity mismatch'):
                    select_artifacts(**fixture)
        fixture = self._partial_rerun_fixture()
        job = next(job for job in fixture['job_attempts'][1]
                   if job['name'] == 'print-regressions')
        job.update(status='in_progress', conclusion=None, completed_at=None)
        with self.assertRaisesRegex(SelectionError, 'did not succeed'):
            select_artifacts(**fixture)


if __name__ == '__main__':
    unittest.main()
