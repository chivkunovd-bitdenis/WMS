"""Exact historical fixture deltas replayed in isolated Git repositories."""

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "checker", Path(__file__).with_name("check_task_documents.py")
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
FIXTURES = json.loads((Path(__file__).parent / "tests/fixtures/wms652_fixture_corrections.json").read_text())


class FixtureChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Regression fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.base = self.commit("base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, subject):
        self.git("add", ".")
        self.git("commit", "-qm", subject, "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def setup_chain(self, task="WMS-663", second=True, mutate=None, extra=False):
        self.git("checkout", "--quiet", self.base)
        names = (["wms663-uuid-before-expire", "wms663-exemplar-save-selector"]
                 if task == "WMS-663" else ["wms517-uuid-before-rollback"])
        if task == "WMS-517":
            companion = FIXTURES["wms517-legacy-sales-companion"]
            self.write(companion["path"], companion["before"])
            self.commit("legacy fixture exists before contract")
        for name in names:
            item = FIXTURES[name]
            self.write(item["path"], item["before"])
        original = self.commit(f"{task}: контракт тестов")
        entries = []
        source = original
        groups = [names]
        if task == "WMS-517" and second:
            groups.append(["wms517-explicit-sales-fixture"])
        for group in groups:
            files = []
            for name in group:
                item = FIXTURES[name]
                text = item["after"]
                if mutate:
                    text = mutate(item["path"], text)
                self.write(item["path"], text)
                files.append({"path": item["path"], "transform": name,
                              "before_blob": self.blob(item["before"]),
                              "after_blob": self.blob(text)})
            companions = []
            if group == ["wms517-explicit-sales-fixture"]:
                item = FIXTURES["wms517-legacy-sales-companion"]
                self.write(item["path"], item["after"])
                companions.append({"path": item["path"], "before_blob": self.blob(item["before"]),
                                   "after_blob": self.blob(item["after"])})
            if extra:
                self.write("unexpected.py", "pass\n")
            correction = self.commit(f"{task}: fixture correction")
            evidence = f"docs/reviews/{task}-{len(entries)}.md"
            self.write(evidence, f"Synthetic independent Astra high PASS of {source} -> {correction}\n")
            evidence_commit = self.commit("record synthetic review")
            entries.append({"contract_commit": original, "source_commit": source,
                            "correction_commit": correction, "files": files,
                            "companion_files": companions,
                            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS",
                                       "source_commit": source, "correction_commit": correction,
                                       "evidence": evidence, "evidence_commit": evidence_commit,
                                       "evidence_blob": self.git("rev-parse", f"HEAD:{evidence}")}})
            source = correction
        return {"task": task, "fixture_corrections": entries}

    def blob(self, text):
        return subprocess.check_output(["git", "hash-object", "--stdin"], input=text, text=True, cwd=self.root).strip()

    def save(self, ledger):
        self.write(f"docs/reviews/contract-corrections/{ledger['task']}.json", json.dumps(ledger))
        self.commit("record exact fixture chain")

    def errors(self, ledger):
        self.save(ledger)
        return checker.contract_change_errors(self.root, self.base)

    def test_real_663_correction_of_both_frozen_files_passes(self):
        self.assertEqual(self.errors(self.setup_chain()), [])

    def test_real_517_two_deltas_same_frozen_file_and_exact_companion_pass(self):
        self.assertEqual(self.errors(self.setup_chain("WMS-517")), [])

    def test_real_517_singleton_uuid_fixture_passes(self):
        self.assertEqual(self.errors(self.setup_chain("WMS-517", second=False)), [])

    def test_reject_changed_assertions_names_parametrization_skip_and_control_flow(self):
        source = FIXTURES["wms663-uuid-before-expire"]["after"]
        mutations = [
            lambda s: s.replace('assert target["is_rnpt_absent"] is True', 'assert True'),
            lambda s: s.replace("test_wms663_explicit_choice", "test_replaced_choice"),
            lambda s: s.replace("async def test_wms663_explicit_choice", "@pytest.mark.skip\nasync def test_wms663_explicit_choice"),
            lambda s: s.replace("async def test_wms663_explicit_choice", "@pytest.mark.xfail\nasync def test_wms663_explicit_choice"),
            lambda s: s.replace("async def test_wms663_explicit_choice", "@pytest.mark.parametrize('unused', [1])\nasync def test_wms663_explicit_choice"),
            lambda s: s.replace("    db_session.expire_all()", "    return\n    db_session.expire_all()"),
            lambda s: "def test_replacement(): assert True\n",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation(source)[:80]):
                self.assertNotEqual(mutation(source), source)
                ledger = self.setup_chain(mutate=lambda p, s: mutation(s) if p.endswith('.py') else s)
                self.assertTrue(self.errors(ledger))

    def test_reject_dom_assertion_skip_and_selector_substitution(self):
        for old, new in [("expect(requests).toContainEqual", "expect([]).toContainEqual"),
                         ("it(", "it.skip("), ("it(", "it.only("),
                         ("SKU 663001", "SKU 999999")]:
            with self.subTest(new=new):
                ledger = self.setup_chain(mutate=lambda p, s: s.replace(old, new) if p.endswith('.tsx') else s)
                self.assertTrue(self.errors(ledger))

    def test_reject_wrong_source_blobs_extra_files_and_missing_or_rebound_review(self):
        ledger = self.setup_chain()
        variants = []
        for field in ["source_commit", "contract_commit"]:
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0][field] = self.base
            variants.append(changed)
        for field in ["before_blob", "after_blob"]:
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["files"][0][field] = "f" * 40
            variants.append(changed)
        for field, value in [("model", "gpt-6.1-sol"), ("effort", "low"), ("verdict", "FAIL"),
                             ("source_commit", self.base), ("correction_commit", self.base),
                             ("evidence_commit", self.base), ("evidence_blob", "f" * 40),
                             ("evidence", "docs/reviews/missing.md")]:
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["review"][field] = value
            variants.append(changed)
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"][0].pop("review")
        variants.append(changed)
        for changed in variants:
            with self.subTest(ledger=changed):
                self.assertTrue(self.errors(changed))
        self.assertTrue(self.errors(self.setup_chain(extra=True)))

    def test_reject_later_head_mutation_review_mutation_and_unrecorded_chain_gap(self):
        ledger = self.setup_chain("WMS-517")
        self.save(ledger)
        self.assertEqual(checker.contract_change_errors(self.root, self.base), [])
        path = ledger["fixture_corrections"][-1]["files"][0]["path"]
        self.write(path, (self.root / path).read_text() + "\n# later mutation\n")
        self.commit("later mutation")
        self.assertTrue(checker.contract_change_errors(self.root, self.base))
        ledger = self.setup_chain("WMS-517")
        ledger["fixture_corrections"] = ledger["fixture_corrections"][1:]
        self.assertTrue(self.errors(ledger))
        ledger = self.setup_chain()
        self.save(ledger)
        evidence = ledger["fixture_corrections"][0]["review"]["evidence"]
        self.write(evidence, "edited review")
        self.commit("review edited")
        self.assertTrue(checker.contract_change_errors(self.root, self.base))

    def test_reject_business_assertion_migration_427fc2(self):
        ledger = self.setup_chain("WMS-517", second=False)
        entry = ledger["fixture_corrections"][0]
        entry["correction_commit"] = "427fc2cba5d09c78c691ca12277e66cff804fc69"
        self.assertTrue(self.errors(ledger))


if __name__ == "__main__":
    unittest.main()
