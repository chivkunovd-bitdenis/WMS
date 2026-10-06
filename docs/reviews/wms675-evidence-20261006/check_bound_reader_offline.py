"""Bounded offline checks for WMS-675 evidence projection; no app settings or network."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('wms675_reader', HERE / 'collect_ozon_bound.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ProjectionChecks(unittest.TestCase):
    def card(self):
        return {'result': {'posting_number': '0113371235-0054-3', 'status': 'delivering',
            'substatus': 'posting_received', 'products': [{'sku': 1697770458, 'quantity': 1, 'offer_id': 'article'}],
            'related_postings': {'related_posting_numbers': []}}}

    def test_only_allowlisted_fields_survive(self):
        raw = self.card()
        raw['result'].update(customer={'secret': 'SENSITIVE_FIXTURE'},
                             addressee={'address': 'SENSITIVE_FIXTURE'}, financial_data={'value': 'SENSITIVE_FIXTURE'},
                             legal_info={'value': 'SENSITIVE_FIXTURE'}, barcodes={'value': 'SENSITIVE_FIXTURE'})
        raw['result']['products'][0].update(exemplars=['SENSITIVE_FIXTURE'], name='SENSITIVE_FIXTURE')
        raw['result']['related_postings']['extra'] = 'SENSITIVE_FIXTURE'
        raw['result']['cancellation'] = {'cancel_reason_id': 42, 'cancelled_after_ship': True, 'extra': 'SENSITIVE_FIXTURE'}
        projected = reader.projection(raw)
        self.assertNotIn('SENSITIVE_FIXTURE', json.dumps(projected))
        self.assertEqual(projected['products'], [{'sku': 1697770458, 'quantity': 1, 'offer_id': 'article'}])
        self.assertTrue(projected['related_postings_present'])

    def test_returned_children_only_and_weight_links_preserved(self):
        raw = self.card()
        raw['result']['related_postings']['related_posting_numbers'] = ['0113371235-0054-4']
        raw['result']['related_weight_postings'] = ['0113371235-0054-5']
        projected = reader.projection(raw)
        self.assertEqual(projected['related_postings']['related_posting_numbers'], ['0113371235-0054-4'])
        self.assertEqual(projected['related_weight_postings'], ['0113371235-0054-5'])

    def test_missing_split_is_distinct_from_confirmed_empty(self):
        raw = self.card()
        del raw['result']['related_postings']
        self.assertFalse(reader.projection(raw)['related_postings_present'])

    def test_invalid_quantities_and_links_fail(self):
        for quantity in (True, 0, -1, '1'):
            raw = self.card()
            raw['result']['products'][0]['quantity'] = quantity
            with self.assertRaises(ValueError):
                reader.projection(raw)
        for links in (['../escape'], ['0113371235-0054-4'] * 2, None):
            raw = self.card()
            raw['result']['related_postings']['related_posting_numbers'] = links
            with self.assertRaises(ValueError):
                reader.projection(raw)

    def test_raw_errors_are_suppressed(self):
        self.assertEqual(reader.failure_code(RuntimeError('SENSITIVE_FIXTURE')), 'details_suppressed')
        self.assertEqual(reader.failure_code(RuntimeError('draft_composition_changed')), 'draft_composition_changed')

    def test_cached_matrix_never_becomes_proof_or_zero_delta(self):
        pending = json.loads((HERE / 'recovery_plan_pending.json').read_text())
        self.assertEqual(len(pending['positions']), 31)
        self.assertEqual(sum(p['quantity'] for p in pending['positions'] if p['cached_candidate']), 26)
        self.assertFalse(pending['mutation_authorized'])
        for p in pending['positions']:
            self.assertIsNone(p['missing_delta'])
            self.assertIsNone(p['proved_unique_quantity'])
            self.assertIsNone(p['fresh_proof'])
        for name, digest in pending['source_hashes'].items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
