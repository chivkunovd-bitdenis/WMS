"""Verify saved WMS-675 addressed plan and sources; no production calls."""
import csv
import hashlib
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'recovery_plan_exact.json').read_text())
REFRESH = HERE / 'accounting-refresh-20261006-attempt1'


class RecoveryEvidenceChecks(unittest.TestCase):
    def test_exact_scope(self):
        self.assertEqual(PLAN['scope'], {'tenant_id':'b80a893b-ab87-42b6-8fd7-6d41502c900f',
            'seller_id':'cf6d31c5-944b-4382-af34-636ca9aa8cc3','supply_id':'b82d1e9a-30d2-4d7b-b52d-9775c3d266e3'})
        self.assertEqual(len({p['order_id'] for p in PLAN['positions']}), 31)
        self.assertEqual(len({p['position_id'] for p in PLAN['positions']}), 31)
        for p in PLAN['positions']:
            self.assertEqual(p['quantity'], 1)
            self.assertEqual(p['recipe_source']['product_id'], p['product_id'])

    def test_external_proofs(self):
        for p in PLAN['positions']:
            data = (HERE / p['evidence_file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), p['evidence_sha256'])
            proof = json.loads(data)
            card = proof['card']
            self.assertEqual(proof['http_status'], 200)
            self.assertEqual(card['posting_number'], p['posting_number'])
            self.assertEqual(card['products'], [{'sku':p['sku'], 'quantity':1, 'offer_id':p['offer_id']}])
            self.assertFalse(card['related_postings']['related_posting_numbers'])
            self.assertFalse(card['related_weight_postings'])
        self.assertEqual(sum(p['proved_unique_quantity'] for p in PLAN['positions']), 26)
        excluded = [p for p in PLAN['positions'] if p['ozon_status'] in {'cancelled','awaiting_packaging'}]
        self.assertEqual(len(excluded), 5)
        self.assertTrue(all(p['missing_delta']==0 for p in excluded))

    def test_accounting_reserve_billing(self):
        manifest = json.loads((REFRESH/'manifest.json').read_text())
        for query in manifest['queries']:
            self.assertEqual(query['status'], 'ok')
            self.assertEqual(hashlib.sha256((REFRESH/query['csv_file']).read_bytes()).hexdigest(), query['sha256'])
        self.assertEqual(PLAN['totals']['already_conducted_units'], 0)
        self.assertEqual(PLAN['totals']['reserve_before'], 16)
        self.assertEqual(PLAN['totals']['reserve_after_full26'], 1)
        self.assertEqual(PLAN['totals']['existing_billing_entries'], 22)
        self.assertEqual(PLAN['totals']['new_billing_entries_expected'], 30)
        self.assertEqual(PLAN['totals']['existing_operation_facts'], 11)
        for name in ['unlinked_fbs_movements','new_history_attribution','other_negative_since_audit']:
            with (REFRESH/(name+'.csv')).open() as source:
                self.assertEqual(list(csv.DictReader(source)), [])
        for p in PLAN['positions']:
            self.assertEqual(p['already_conducted_quantity'], 0)
            if p['ozon_status']=='delivered':
                self.assertEqual({b['service_code'] for b in p['existing_billing']}, {'fbs_order','packing'})
                self.assertEqual(p['missing_billing_services'], [])
                self.assertFalse(p['new_operation_fact_required'])

    def test_addressed_plan_remains_blocked_without_forged_targets(self):
        self.assertEqual(PLAN['totals']['missing_delta'], 26)
        self.assertEqual(PLAN['totals']['current662_missing_delta'], 11)
        self.assertEqual(PLAN['totals']['blocked_by_substatus_units'], 15)
        self.assertEqual(sum(p['missing_delta'] for p in PLAN['positions']), 26)
        for p in PLAN['positions']:
            self.assertEqual(p['missing_delta'], max(0,p['proved_unique_quantity']-p['already_conducted_quantity']))
            self.assertFalse(p['mutation_authorized'])
        self.assertEqual(PLAN['actual_recovery'], 'NOT_PERFORMED')
        self.assertIn('WAIT_662_SUBSTATUS_FIX', PLAN['execution_state'])

    def test_no_actual_recovery_claim(self):
        self.assertFalse(PLAN['mutation_authorized'])
        self.assertEqual(PLAN['actual_recovery'], 'NOT_PERFORMED')
        manifest = json.loads((REFRESH/'manifest.json').read_text())
        self.assertEqual(manifest['writes'], 0)
        self.assertEqual(manifest['external_calls'], 0)
        for name in PLAN['operation_sequence']:
            self.assertNotIn('deliver_supply(', name)


if __name__ == '__main__':
    unittest.main()
