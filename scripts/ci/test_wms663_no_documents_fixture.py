"""Exact one-line F3 fixture correction; no business expectation replacement."""
import copy
import subprocess
import unittest
from unittest.mock import patch

import test_fixture_contract_corrections as harness

checker = harness.checker
NAME = 'wms663-known-no-documents-complete-requirements'
PATH = 'frontend/src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx'
ORIGINAL = '68c3bd3052e201c16b8f9a1d0fe1282cc91615c3'
CORRECTION = 'a08c98f77d9f39d0ed7991bb8fd6f19f21ebef62'


class NoDocumentsFixtureTests(unittest.TestCase):
    def setUp(self):
        self.repo = harness.FixtureChainTests()
        self.repo.setUp()
        self.addCleanup(self.repo.doCleanups)
        self.before = subprocess.check_output(['git', 'show', f'{ORIGINAL}:{PATH}'], text=True)
        self.after = subprocess.check_output(['git', 'show', f'{CORRECTION}:{PATH}'], text=True)

    def setup(self, text=None, extra=False):
        r = self.repo
        r.write(PATH, self.before)
        original = r.commit('WMS-663: контракт тестов')
        r.write(PATH, text or self.after)
        if extra:
            r.write('unexpected.py', 'pass\n')
        correction = r.commit('exact F3 fixture correction')
        evidence = 'docs/reviews/synthetic-F3-review.md'
        r.write(evidence, f'Synthetic Sol6.1 high PASS {original} -> {correction}\n')
        evidence_commit = r.commit('separate synthetic independent review')
        self.entry = {'contract_commit': original, 'source_commit': original,
                      'correction_commit': correction,
                      'files': [{'path': PATH, 'transform': NAME, 'before_blob': r.blob(self.before),
                                 'after_blob': r.blob(text or self.after)}], 'companion_files': [],
                      'review': {'model': 'gpt-6.1-sol', 'effort': 'high', 'verdict': 'PASS',
                                 'source_commit': original, 'correction_commit': correction,
                                 'evidence': evidence, 'evidence_commit': evidence_commit,
                                 'evidence_blob': checker.git_blob(r.root, evidence_commit, evidence)}}
        return {'task': 'WMS-663', 'fixture_corrections': [self.entry]}

    def errors(self, ledger):
        self.repo.save(ledger)
        return checker.contract_change_errors(self.repo.root, self.repo.base)

    def test_pair_is_exactly_one_fixture_field_and_all_expectations_identical(self):
        before = "B: { version: 7, state: 'editable', absence_selected: false, products: [{"
        after = before.replace('products:', 'requirements_complete: true, products:')
        self.assertEqual(self.before.count(before), 1)
        self.assertEqual(self.before.replace(before, after), self.after)
        self.assertEqual(checker.FIXTURE_BLOB_PAIRS[NAME], (
            'WMS-663', PATH, self.repo.blob(self.before), self.repo.blob(self.after)))

    def test_strict_pair_passes_only_with_review(self):
        ledger = self.setup()
        self.assertEqual(self.errors(ledger), [])
        self.entry['review']['verdict'] = 'PENDING'
        self.assertTrue(self.errors(ledger))

    def test_before_pair_gate_rejects_same_correction(self):
        ledger = self.setup()
        self.assertEqual(self.errors(ledger), [])
        old = copy.deepcopy(checker.FIXTURE_BLOB_PAIRS)
        del old[NAME]
        with patch.dict(checker.FIXTURE_BLOB_PAIRS, old, clear=True):
            self.assertTrue(checker.contract_change_errors(self.repo.root, self.repo.base))

    def test_weakening_assertion_or_other_bytes_rejected(self):
        ledger = self.setup(self.after.replace('toHaveLength(0)', 'toHaveLength(1)'))
        self.assertTrue(self.errors(ledger))

    def test_extra_file_wrong_before_and_unreviewed_head_rejected(self):
        ledger = self.setup(extra=True)
        self.assertTrue(self.errors(ledger))
        self.entry['files'][0]['before_blob'] = 'a'*40
        self.assertTrue(self.errors(ledger))

    def test_mode_and_later_blob_mutation_rejected(self):
        ledger = self.setup()
        self.assertEqual(self.errors(ledger), [])
        self.repo.write(PATH, self.after + '// unreviewed change\n')
        self.repo.commit('unreviewed mutation')
        self.assertTrue(self.errors(ledger))
        self.repo.write(PATH, self.after)
        self.repo.commit('restore bytes')
        (self.repo.root / PATH).chmod(0o755)
        self.repo.commit('mode change')
        self.assertTrue(self.errors(ledger))


if __name__ == '__main__':
    unittest.main()
