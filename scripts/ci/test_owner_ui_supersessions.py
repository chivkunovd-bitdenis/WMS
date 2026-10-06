"""Semantic owner supersession regressions in disposable, synthetic Git repos."""
import copy
import json
import subprocess
import types
import unittest
from unittest.mock import patch

import test_fixture_contract_corrections as harness

checker = harness.checker


class OwnerSupersessionTests(unittest.TestCase):
    def setUp(self):
        self.repo = harness.FixtureChainTests()
        self.repo.setUp()
        self.addCleanup(self.repo.doCleanups)

    def setup(self, legacy=False, second=True):
        r = self.repo
        task = 'WMS-662' if legacy else 'WMS-663'
        if legacy:
            r.write('backend/tests/legacy.py', 'old legacy\n')
            old = r.commit(f'{task}: контракт тестов')
            r.write('backend/tests/legacy.py', 'corrected legacy\n')
            fixed = r.commit('exact legacy correction')
            ledger = {'task': task, 'contract_commit': old, 'correction_commit': fixed,
                      'files': ['backend/tests/legacy.py'],
                      'review': {'model': 'gpt-6.1-sol', 'effort': 'high', 'verdict': 'PASS'}}
            path = 'frontend/src/screens/v2/c19.test.tsx'
            r.write(path, 'old UI\n')
            original = r.commit(f'{task}: контракт тестов')
            prior = original
        else:
            ledger = r.setup_chain()
            original = ledger['fixture_corrections'][0]['contract_commit']
            prior = ledger['fixture_corrections'][-1]['correction_commit']
            path = ledger['fixture_corrections'][0]['files'][1]['path']
        before = checker.git_blob(r.root, 'HEAD', path)
        owner_path = 'docs/reviews/synthetic-owner.md'
        r.write(owner_path, 'Synthetic owner: one checkbox, baseline rollback.\n')
        owner_commit = r.commit('record synthetic owner request')
        owner = {'commit': owner_commit, 'path': owner_path,
                 'blob': checker.git_blob(r.root, owner_commit, owner_path)}
        source = owner_commit
        r.write(path, 'new explicit owner UI expectations\n')
        correction = r.commit('owner semantic contract supersession')
        changes = [[correction, checker.git_blob(r.root, correction, path)]]
        if second:
            r.write(path, 'new owner UI uses existing error channel\n')
            correction = r.commit('owner feedback contract refinement')
            changes.append([correction, checker.git_blob(r.root, correction, path)])
        allowed = {'contract_commit': original, 'prior_commit': prior, 'source_commit': source,
                   'path': path, 'before_blob': before, 'changes': changes}
        review_path = 'docs/reviews/synthetic-sol-review.md'
        r.write(review_path, f'Synthetic Sol6.1 high PASS exact {source} -> {correction}\n')
        evidence_commit = r.commit('record separate synthetic review')
        entry = dict(allowed, owner_request=owner, review={
            'model': 'gpt-6.1-sol', 'effort': 'high', 'verdict': 'PASS',
            'source_commit': source, 'correction_commit': correction,
            'evidence': review_path, 'evidence_commit': evidence_commit,
            'evidence_blob': checker.git_blob(r.root, evidence_commit, review_path),
        })
        ledger['owner_supersessions'] = [entry]
        self.addCleanup(patch.stopall)
        patch.dict(checker.OWNER_UI_SUPERSESSIONS, {task: allowed}, clear=True).start()
        patch.dict(checker.OWNER_UI_REQUEST, owner, clear=True).start()
        self.task, self.ledger, self.entry, self.path = task, ledger, entry, path
        return ledger

    def errors(self, ledger=None):
        r = self.repo
        ledger = ledger or self.ledger
        r.write(f'docs/reviews/contract-corrections/{self.task}.json', json.dumps(ledger))
        r.commit('publish synthetic ledger')
        return checker.contract_change_errors(r.root, r.base)

    def test_fixture_chain_with_semantic_supersession(self):
        self.setup()
        self.assertEqual(self.errors(), [])

    def test_pre_fix_gate_rejects_the_same_semantic_supersession(self):
        self.setup()
        self.assertEqual(self.errors(), [])
        old = types.ModuleType('pre_fix_gate')
        source = subprocess.check_output([
            'git', 'show', '4c9e1238c85a50a9238bc109651c79cac5f10e03:scripts/ci/check_task_documents.py',
        ], text=True)
        exec(compile(source, '<pre-fix checker>', 'exec'), old.__dict__)
        self.assertTrue(old.contract_change_errors(self.repo.root, self.repo.base))

    def test_legacy_single_file_format_remains_legacy_and_ui_can_be_superseded(self):
        self.setup(legacy=True, second=False)
        self.assertNotIn('corrections', self.ledger)
        self.assertEqual(self.errors(), [])

    def test_pending_cannot_pass(self):
        self.setup()
        self.entry['review']['verdict'] = 'PENDING'
        self.assertTrue(self.errors())

    def test_missing_or_wrong_owner_proof_rejected(self):
        self.setup()
        del self.entry['owner_request']
        self.assertTrue(self.errors())

    def test_mutated_owner_artifact_rejected(self):
        self.setup()
        self.repo.write(self.entry['owner_request']['path'], 'owner text edited\n')
        self.repo.commit('mutate owner proof')
        self.assertTrue(self.errors())

    def test_mutated_review_artifact_rejected(self):
        self.setup()
        self.repo.write(self.entry['review']['evidence'], 'PASS some other source\n')
        self.repo.commit('mutate review proof')
        self.assertTrue(self.errors())

    def test_wrong_review_model_effort_and_target_rejected(self):
        self.setup()
        for field, value in [('model', 'gpt-6-astra'), ('effort', 'low'),
                             ('correction_commit', self.entry['source_commit'])]:
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.ledger)
                ledger['owner_supersessions'][0]['review'][field] = value
                self.assertTrue(self.errors(ledger))

    def test_review_text_must_name_full_final_sha(self):
        self.setup()
        r = self.repo
        review = self.entry['review']
        r.write(review['evidence'], f'Synthetic PASS {review["correction_commit"][:9]}\n')
        review['evidence_commit'] = r.commit('new review without full target')
        review['evidence_blob'] = checker.git_blob(r.root, 'HEAD', review['evidence'])
        self.assertTrue(self.errors())

    def test_fail_artifact_cannot_be_labelled_pass_in_ledger(self):
        self.setup()
        review = self.entry['review']
        self.repo.write(review['evidence'], f'Synthetic FAIL {review["correction_commit"]}\n')
        review['evidence_commit'] = self.repo.commit('negative independent review')
        review['evidence_blob'] = checker.git_blob(self.repo.root, 'HEAD', review['evidence'])
        self.assertTrue(self.errors())

    def test_wrong_old_blob_path_or_omitted_transition_rejected(self):
        self.setup()
        for field, value in [('before_blob', 'a'*40), ('path', 'backend/tests/new.py'),
                             ('changes', self.entry['changes'][-1:])]:
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.ledger)
                ledger['owner_supersessions'][0][field] = value
                self.assertTrue(self.errors(ledger))

    def test_untouched_fixture_backend_is_still_frozen(self):
        self.setup()
        path = self.ledger['fixture_corrections'][0]['files'][0]['path']
        self.repo.write(path, 'weaken unrelated frozen backend\n')
        self.repo.commit('unrelated expectation mutation')
        self.assertTrue(self.errors())

    def test_legacy_whole_contract_array_is_still_rejected(self):
        self.setup(legacy=True)
        ledger = copy.deepcopy(self.ledger)
        old = {k: ledger.pop(k) for k in ('contract_commit', 'correction_commit', 'files', 'review')}
        ledger['corrections'] = [old]
        self.assertTrue(self.errors(ledger))

    def test_post_supersession_mutate_then_revert_still_rejected(self):
        self.setup()
        r = self.repo
        original = (r.root / self.path).read_text()
        r.write(self.path, 'temporary weaken expectations\n')
        r.commit('forbidden later mutation')
        r.write(self.path, original)
        r.commit('dummy reapply')
        self.assertTrue(self.errors())

    def test_mode_change_and_duplicate_entry_rejected(self):
        self.setup()
        duplicate = copy.deepcopy(self.ledger)
        duplicate['owner_supersessions'].append(copy.deepcopy(self.entry))
        self.assertTrue(self.errors(duplicate))
        self.repo.git('update-index', '--chmod=+x', self.path)
        self.repo.git('commit', '-qm', 'forbidden executable UI file')
        self.assertTrue(self.errors())

    def test_historical_fixture_review_is_not_bypassed(self):
        self.setup()
        self.ledger['fixture_corrections'][0]['review']['verdict'] = 'PENDING'
        self.assertTrue(self.errors())


if __name__ == '__main__':
    unittest.main()
