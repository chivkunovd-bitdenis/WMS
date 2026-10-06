"""WMS-652/517 explicit follow-up workflow contracts before command changes."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE_BINDING = ROOT / 'scripts/ci/tests/fixtures/wms652_source_binding_transition.json'
PRODUCT_SCOPE_PREFIX = 'python scripts/ci/product_scope.py --root . --trusted-ref '


class ReleaseCommandContracts(unittest.TestCase):
    def guard_section(self, raw):
        return raw.split('\n  guards:\n', 1)[1].split('\n  printer-windows:', 1)[0]

    def source_binding(self):
        return json.loads(SOURCE_BINDING.read_text())

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
        return trusted_ref

    def test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        guard = self.guard_section(raw)
        self.assertIn('python scripts/ci/product_scope.py --root . --trusted-ref d61805978b3e7878d1056c99b4e6e0823edf49a5', guard)
        self.assertIn('pytest -q scripts/ci/tests/test_product_scope.py --junitxml=', guard)

    def test_pending_final_source_binding_keeps_existing_exact_reference(self):
        binding = self.source_binding()
        self.assertEqual(binding['status'], 'pending-final-independent-freeze')
        self.assertIsNone(binding['final_reviewed_source'])
        self.assertEqual(binding['accepted_reviewed_sources'], [binding['current_reviewed_source']])
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        self.assertEqual(self.assert_binding_is_independently_reviewed(guard, binding),
                         binding['current_reviewed_source'])

    def test_final_source_contract_refuses_head_self_selection_and_unreviewed_reference(self):
        binding = self.source_binding()
        guard = self.guard_section((ROOT/'.github/workflows/ci.yml').read_text())
        current = self.trusted_reference(guard)
        for rejected in [*binding['self_selecting_references'], binding['unreviewed_candidate_source']]:
            with self.subTest(rejected=rejected):
                candidate_guard = guard.replace(PRODUCT_SCOPE_PREFIX + current,
                                                PRODUCT_SCOPE_PREFIX + rejected)
                with self.assertRaises(AssertionError):
                    self.assert_binding_is_independently_reviewed(candidate_guard, binding)

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
