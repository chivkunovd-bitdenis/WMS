"""Fifth exact pair and negative bypass probes; no product tests are executed."""

import copy
import json
import unittest
from pathlib import Path

import test_fixture_contract_corrections as harness

NAME = "wms663-complete-positive-status-fixtures"
DATA = json.loads((Path(__file__).parent / "tests/fixtures/wms663_positive_status.json").read_text())
checker = harness.checker


class PositiveFixtureChainTests(unittest.TestCase):
    def setUp(self):
        self.repo = harness.FixtureChainTests()
        self.repo.setUp()
        self.addCleanup(self.repo.doCleanups)

    def chain(self, mutation=None, gap=False, extra=False, mode=False):
        repo = self.repo
        ledger = repo.setup_chain()
        first = ledger["fixture_corrections"][0]
        path = first["files"][0]["path"]
        if gap:
            repo.write(path, DATA["before"] + "\n# unreviewed mutation\n")
            repo.commit("unreviewed test change")
            repo.write(path, DATA["before"])
            repo.commit("restore bytes without review")
        source = repo.commit("product delta leaves frozen files unchanged")
        after = mutation(DATA["after"]) if mutation else DATA["after"]
        repo.write(path, after)
        if mode:
            (repo.root / path).chmod(0o755)
        repo.write(DATA["handoff_path"], DATA["handoff"])
        if extra:
            repo.write("unexpected.py", "pass\n")
        correction = repo.commit("WMS-663: positive fixture correction")
        evidence = "docs/reviews/positive-fixture.md"
        repo.write(evidence, f"Synthetic Astra high PASS {source} -> {correction}\n")
        review_commit = repo.commit("synthetic independent review")
        ledger["fixture_corrections"].append({
            "contract_commit": first["contract_commit"], "source_commit": source,
            "correction_commit": correction,
            "files": [{"path": path, "transform": NAME,
                       "before_blob": repo.blob(DATA["before"]),
                       "after_blob": repo.blob(after)}],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS",
                       "source_commit": source, "correction_commit": correction,
                       "evidence": evidence, "evidence_commit": review_commit,
                       "evidence_blob": repo.git("rev-parse", f"HEAD:{evidence}")},
        })
        return ledger

    def test_fifth_pair_and_sequential_file_baselines(self):
        ledger = self.chain()
        self.repo.save(ledger)
        self.assertEqual(checker.contract_change_errors(self.repo.root, self.repo.base), [])
        first, second = ledger["fixture_corrections"]
        baselines, errors = checker.exact_fixture_corrections(
            self.repo.root, "WMS-663", first["contract_commit"], ledger)
        self.assertEqual(errors, [])
        self.assertEqual(baselines, {
            first["correction_commit"]: {first["files"][1]["path"]},
            second["correction_commit"]: {second["files"][0]["path"]},
        })
        self.assertEqual(len(checker.FIXTURE_BLOB_PAIRS), 5)

    def test_reject_gap_reordering_missing_review_and_false_source(self):
        ledger = self.chain()
        self.assertEqual(self.repo.errors(ledger), [])
        variants = []
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"].reverse()
        variants.append(changed)
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"].pop(0)
        variants.append(changed)
        for field, value in [("review", None), ("source_commit", self.repo.base)]:
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][1][field] = value
            variants.append(changed)
        for changed in variants:
            self.assertTrue(self.repo.errors(changed))
        self.assertTrue(self.repo.errors(self.chain(gap=True)))

    def test_reject_assertion_name_skip_parameter_and_control_flow_changes(self):
        for old, new in [
            ('assert target["is_rnpt_absent"] is True', 'assert True'),
            ("test_wms663_explicit_choice", "test_replaced_choice"),
            ("async def test_wms663_explicit_choice", "@pytest.mark.skip\nasync def test_wms663_explicit_choice"),
            ("async def test_wms663_explicit_choice", "@pytest.mark.parametrize('unused', [1])\nasync def test_wms663_explicit_choice"),
            ("    db_session.expire_all()", "    return\n    db_session.expire_all()"),
        ]:
            with self.subTest(new=new):
                self.assertIn(old, DATA["after"])
                self.assertTrue(self.repo.errors(self.chain(mutation=lambda text: text.replace(old, new))))

    def test_reject_extra_paths_handoff_mutation_mode_and_wrong_full_review_sha(self):
        ledger = self.chain()
        self.assertEqual(self.repo.errors(ledger), [])
        self.repo.write(DATA["handoff_path"], DATA["handoff"] + "changed\n")
        self.repo.commit("alter exact correction handoff")
        self.assertTrue(self.repo.errors(ledger))
        self.assertTrue(self.repo.errors(self.chain(extra=True)))
        self.assertTrue(self.repo.errors(self.chain(mode=True)))
        ledger = self.chain()
        entry = ledger["fixture_corrections"][1]
        review = entry["review"]
        sha = entry["correction_commit"]
        wrong = sha[:9] + ("a" if sha[9] != "a" else "b") + sha[10:]
        self.repo.write(review["evidence"], f"PASS {wrong}\n")
        review["evidence_commit"] = self.repo.commit("review a different full SHA")
        review["evidence_blob"] = self.repo.git("rev-parse", f"HEAD:{review['evidence']}")
        self.assertTrue(self.repo.errors(ledger))
