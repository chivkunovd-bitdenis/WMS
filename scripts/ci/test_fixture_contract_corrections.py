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

WMS517_CONTRACT_SOURCE = "3c3c1b69c15cb611c7d256971f9c85ebb9d1ae60"
WMS517_DECOY_COMMIT = "28671d78ce431a6fc32c357a6eee34f769ce6192"
WMS517_CONTRACT_SUBJECT = "WMS-517: align recovery tests with finance archive"
WMS517_CONTRACT_CHANGED_PATHS = {
    "backend/tests/test_withdrawal_ledger.py",
    "backend/tests/test_wms517_raw_integer_price.py",
    "backend/tests/test_wms517_raw_numeric_price.py",
    "backend/tests/test_wms517_sales_contract.py",
    "backend/tests/test_wms517_sales_partial_decimal_regressions.py",
    "backend/tests/test_wms537_draft_supply_stickers.py",
    "docs/requirements/WMS-517.md",
    "docs/requirements/WMS-537.md",
    "guards/PROCESS_CONTRACTS.json",
}
WMS517_HISTORY_COMMIT = "30de00e5f70c3fde354036702aa921ebaab7fd65"
WMS517_HISTORY_PARENT = "f2f9b9b835e7e11cabcce1c693e283072417bac2"
WMS517_REVIEW_COMMIT = "86df6d2a8122c7e43ad14e6aa40d8303f3eb4fa3"
WMS517_REVIEW_PATH = "docs/evidence/WMS-517/incident-20261008/review-fixture-correction.md"
WMS517_REVIEW_BLOB = "a07eb01b2907b04828d4caa31f144ba78bd4da3f"
WMS517_LEDGER_PATH = "backend/tests/test_withdrawal_ledger.py"
WMS517_FROZEN_PATHS = {WMS517_LEDGER_PATH}
WMS517_BEFORE_BLOB = "ac14733de2530eb4e0f4ae285cab806d5eec3755"
WMS517_AFTER_BLOB = "f20342fe34f3c7d05b96960028087dd2968d0960"
WMS517_GUARD_PATH = "guards/PROCESS_CONTRACTS.json"
WMS517_GUARD_BEFORE_BLOB = "4f80f9ea11d7e51c1bd6a64e7e99a4d362472125"
WMS517_GUARD_AFTER_BLOB = "6daab1ccf12d79d2e462bcb651c55692fbd06151"
WMS517_LEDGER_TRANSFORM = "wms517-withdrawal-ledger-30de-exact-fixture"
WMS517_COMPANIONS = [
    {"path": WMS517_GUARD_PATH, "before_blob": WMS517_GUARD_BEFORE_BLOB, "after_blob": WMS517_GUARD_AFTER_BLOB},
    {"path": "backend/tests/test_wb_catalog_schedule.py", "before_blob": "b22007910e910a102105982e3531d36a2930c344", "after_blob": "cce26bacce70ae86c65c1febfd23f915df58958a"},
    {"path": "backend/tests/test_wms666_packing_sticker_request.py", "before_blob": "fa797ead6126fa239cdfa39a306a08a02287b222", "after_blob": "7b7bd5bfc36050cc697dd84500255a7dc04a26b7"},
    {"path": "docs/requirements/WMS-666.md", "before_blob": "57577022c980e9efbee01d06cf9e14330eb2a871", "after_blob": "4a79c1858e870f0e497a17a2a100fc828e23cc63"},
    {"path": "docs/requirements/WMS-689.md", "before_blob": "6a4243254c80844602b57170f8ed716f4f22f2f2", "after_blob": "0a0a9a8744f1892e9cb330324f8f88674c691592"},
]
REPOSITORY = Path(__file__).resolve().parents[2]


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

    def test_actual_sol61_high_review_accepts_exact_fixture_delta(self):
        ledger = self.setup_chain()
        ledger["fixture_corrections"][0]["review"]["model"] = "gpt-6.1-sol"
        self.assertEqual(self.errors(ledger), [])

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
        for field, value in [("model", "unknown-reviewer"), ("effort", "low"), ("verdict", "FAIL"),
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

    def historical_mode(self, revision, path):
        result = subprocess.check_output(
            ["git", "ls-tree", "-z", "--full-tree", revision, "--", path],
            cwd=REPOSITORY,
            text=True,
        )
        metadata, found_path = result.removesuffix("\0").split("\t", 1)
        self.assertEqual(found_path, path)
        return metadata.split()[0]

    def wms517_actual_history_ledger(self):
        source = WMS517_CONTRACT_SOURCE
        correction = WMS517_HISTORY_COMMIT
        self.assertEqual(
            checker.git(REPOSITORY, "rev-parse", f"{correction}^"),
            WMS517_HISTORY_PARENT,
        )
        self.assertEqual(
            checker.git(REPOSITORY, "show", "-s", "--format=%s", source),
            WMS517_CONTRACT_SUBJECT,
        )
        self.assertEqual(
            checker.commit_changed_paths(REPOSITORY, source),
            WMS517_CONTRACT_CHANGED_PATHS,
        )
        self.assertEqual(
            checker.commit_changed_paths(REPOSITORY, correction),
            {
                WMS517_LEDGER_PATH,
                WMS517_GUARD_PATH,
                *(item["path"] for item in WMS517_COMPANIONS),
            },
        )
        self.assertEqual(
            checker.git_blob(REPOSITORY, WMS517_REVIEW_COMMIT, WMS517_REVIEW_PATH),
            WMS517_REVIEW_BLOB,
        )
        self.assertIn(
            WMS517_REVIEW_PATH,
            checker.commit_changed_paths(REPOSITORY, WMS517_REVIEW_COMMIT),
        )
        self.assertEqual(
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", correction, WMS517_REVIEW_COMMIT],
                cwd=REPOSITORY,
                check=False,
            ).returncode,
            0,
        )

        exact_files = [
            (WMS517_LEDGER_PATH, WMS517_LEDGER_TRANSFORM,
             WMS517_BEFORE_BLOB, WMS517_AFTER_BLOB),
        ]
        files = []
        for path, transform, before, after in exact_files:
            self.assertEqual(checker.git_blob(REPOSITORY, source, path), before)
            self.assertEqual(checker.git_blob(REPOSITORY, WMS517_HISTORY_PARENT, path), before)
            self.assertEqual(checker.git_blob(REPOSITORY, correction, path), after)
            self.assertEqual(self.historical_mode(source, path), "100644")
            self.assertEqual(self.historical_mode(correction, path), "100644")
            files.append({
                "path": path,
                "transform": transform,
                "before_blob": before,
                "after_blob": after,
                "source_mode": "100644",
                "correction_mode": "100644",
            })

        companions = []
        history_files = []
        for item in WMS517_COMPANIONS:
            path = item["path"]
            before, after = item["before_blob"], item["after_blob"]
            self.assertEqual(checker.git_blob(REPOSITORY, WMS517_HISTORY_PARENT, path), before)
            self.assertEqual(checker.git_blob(REPOSITORY, correction, path), after)
            self.assertEqual(self.historical_mode(WMS517_HISTORY_PARENT, path), "100644")
            self.assertEqual(self.historical_mode(correction, path), "100644")
            companions.append({
                "path": path,
                "before_blob": before,
                "after_blob": after,
                "source_mode": "100644",
                "correction_mode": "100644",
            })

        history_files = [
            {
                "path": path,
                "source_mode": self.historical_mode(WMS517_HISTORY_PARENT, path),
                "source_blob": before,
                "correction_mode": self.historical_mode(correction, path),
                "correction_blob": after,
            }
            for path, before, after in [
                (WMS517_LEDGER_PATH, WMS517_BEFORE_BLOB, WMS517_AFTER_BLOB),
                *[(item["path"], item["before_blob"], item["after_blob"])
                  for item in WMS517_COMPANIONS],
            ]
        ]
        return {
            "task": "WMS-517",
            "fixture_corrections": [{
                "contract_commit": source,
                "source_commit": source,
                "correction_commit": correction,
                "legacy_fixture_anchor": {
                    "task": "WMS-517",
                    "commit": source,
                    "subject": WMS517_CONTRACT_SUBJECT,
                    "changed_paths": sorted(WMS517_CONTRACT_CHANGED_PATHS),
                    "frozen_paths": sorted(WMS517_FROZEN_PATHS),
                },
                "files": files,
                "companion_files": companions,
                "historical_fixture_source": {
                    "source_commit": source,
                    "correction_parent": WMS517_HISTORY_PARENT,
                    "correction_commit": correction,
                    "files": history_files,
                    "review": {
                        "model": "gpt-6.1-sol",
                        "effort": "high",
                        "verdict": "PASS",
                        "commit": WMS517_REVIEW_COMMIT,
                        "path": WMS517_REVIEW_PATH,
                        "blob": WMS517_REVIEW_BLOB,
                    },
                },
                "review": {
                    "model": "gpt-6.1-sol",
                    "effort": "high",
                    "verdict": "PASS",
                    "source_commit": source,
                    "correction_commit": correction,
                    "evidence": WMS517_REVIEW_PATH,
                    "evidence_commit": WMS517_REVIEW_COMMIT,
                    "evidence_blob": WMS517_REVIEW_BLOB,
                },
            }],
        }

    def exact_wms517_history_errors(self, ledger):
        return checker.exact_fixture_corrections(
            REPOSITORY,
            "WMS-517",
            WMS517_CONTRACT_SOURCE,
            ledger,
        )[1]

    def test_wms517_3c3_is_an_exact_legacy_fixture_anchor_with_narrow_frozen_scope(self):
        ledger = self.wms517_actual_history_ledger()
        entry = ledger["fixture_corrections"][0]
        anchor = entry["legacy_fixture_anchor"]
        self.assertEqual(anchor["task"], "WMS-517")
        self.assertEqual(anchor["commit"], WMS517_CONTRACT_SOURCE)
        self.assertEqual(anchor["subject"], WMS517_CONTRACT_SUBJECT)
        self.assertEqual(set(anchor["changed_paths"]), WMS517_CONTRACT_CHANGED_PATHS)
        self.assertEqual(set(anchor["frozen_paths"]), WMS517_FROZEN_PATHS)
        self.assertNotIn(WMS517_GUARD_PATH, anchor["frozen_paths"])
        self.assertNotIn("backend/tests/test_wms537_draft_supply_stickers.py", anchor["frozen_paths"])
        self.assertEqual(
            checker.git(REPOSITORY, "show", "-s", "--format=%s", WMS517_CONTRACT_SOURCE),
            WMS517_CONTRACT_SUBJECT,
        )
        self.assertEqual(
            checker.commit_changed_paths(REPOSITORY, WMS517_CONTRACT_SOURCE),
            WMS517_CONTRACT_CHANGED_PATHS,
        )
        self.assertEqual(self.exact_wms517_history_errors(ledger), [])

    def test_wms517_30de_real_six_path_history_and_review_are_admitted(self):
        ledger = self.wms517_actual_history_ledger()
        errors = self.exact_wms517_history_errors(ledger)
        self.assertEqual(
            errors,
            [],
            "the immutable 3c3 -> 30de transition must bind the 30de parent, all six "
            "path/mode/blob pairs, and the 86df independent review artifact",
        )

    def test_wms517_30de_history_rejects_wrong_source_correction_blobs_and_modes(self):
        ledger = self.wms517_actual_history_ledger()
        mutations = []
        for key, value in (("source_commit", WMS517_HISTORY_PARENT),
                           ("correction_commit", WMS517_REVIEW_COMMIT)):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0][key] = value
            mutations.append((key, changed))
        for key, value in (("before_blob", "f" * 40), ("after_blob", "e" * 40),
                           ("source_mode", "100755"), ("correction_mode", "100755"),
                           ("path", "backend/tests/test_withdrawal_orchestration.py")):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["files"][0][key] = value
            mutations.append((key, changed))
        for key, value in (("source_commit", WMS517_HISTORY_PARENT),
                           ("correction_parent", WMS517_CONTRACT_SOURCE),
                           ("correction_commit", WMS517_REVIEW_COMMIT)):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["historical_fixture_source"][key] = value
            mutations.append((f"historical.{key}", changed))
        for index in range(6):
            for field, value in (("source_mode", "100755"), ("source_blob", "f" * 40),
                                 ("correction_mode", "100755"), ("correction_blob", "e" * 40),
                                 ("path", "backend/tests/test_withdrawal_orchestration.py")):
                changed = copy.deepcopy(ledger)
                changed["fixture_corrections"][0]["historical_fixture_source"]["files"][index][field] = value
                mutations.append((f"historical-file.{index}.{field}", changed))
        for key, value in (("commit", WMS517_HISTORY_PARENT),
                           ("commit", WMS517_DECOY_COMMIT),
                           ("subject", "WMS-517: контракт тестов"),
                           ("changed_paths", sorted(WMS517_CONTRACT_CHANGED_PATHS - {WMS517_GUARD_PATH})),
                           ("frozen_paths", sorted(WMS517_FROZEN_PATHS | {WMS517_GUARD_PATH})),
            ("frozen_paths", sorted(WMS517_FROZEN_PATHS | {"backend/tests/test_wms537_draft_supply_stickers.py"}))):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["legacy_fixture_anchor"][key] = value
            mutations.append((f"anchor.{key}", changed))
        for section in ("files", "companion_files"):
            rows = ledger["fixture_corrections"][0][section]
            for index in range(len(rows)):
                for field, value in (("path", "backend/tests/test_withdrawal_orchestration.py"),
                                     ("before_blob", "f" * 40), ("after_blob", "e" * 40),
                                     ("source_mode", "100755"), ("correction_mode", "100755")):
                    changed = copy.deepcopy(ledger)
                    changed["fixture_corrections"][0][section][index][field] = value
                    mutations.append((f"{section}.{index}.{field}", changed))
        for field, value in (("commit", WMS517_HISTORY_PARENT), ("blob", "f" * 40),
                             ("path", "docs/reviews/other.md")):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][0]["historical_fixture_source"]["review"][field] = value
            mutations.append((f"historical-review.{field}", changed))
        for label, changed in mutations:
            with self.subTest(mutation=label):
                self.assertTrue(self.exact_wms517_history_errors(changed))

    def test_wms517_30de_history_rejects_companion_scope_review_rebind_and_expectation_changes(self):
        ledger = self.wms517_actual_history_ledger()
        variants = []
        for transform in (
            lambda entry: entry["companion_files"].pop(),
            lambda entry: entry["companion_files"].append({
                "path": "unexpected.py", "before_blob": None, "after_blob": "f" * 40,
                "source_mode": None, "correction_mode": "100644",
            }),
            lambda entry: entry["review"].update({"source_commit": WMS517_HISTORY_PARENT}),
            lambda entry: entry["review"].update({"correction_commit": WMS517_REVIEW_COMMIT}),
            lambda entry: entry["review"].update({"evidence_commit": WMS517_HISTORY_COMMIT}),
            lambda entry: entry["review"].update({"evidence_blob": "f" * 40}),
        ):
            changed = copy.deepcopy(ledger)
            transform(changed["fixture_corrections"][0])
            variants.append(changed)

        source_text = subprocess.check_output(
            ["git", "show", f"{WMS517_HISTORY_COMMIT}:{WMS517_LEDGER_PATH}"],
            cwd=REPOSITORY,
            text=True,
        )
        mutations = (
            lambda text: text.replace('assert response.status_code == 409', 'assert response.status_code == 200', 1),
            lambda text: text.replace(
                "async def test_api_gates_signatures_scopes_and_never_returns_tokens(",
                "@pytest.mark.skip\nasync def test_api_gates_signatures_scopes_and_never_returns_tokens(", 1,
            ),
        )
        for mutate in mutations:
            changed = copy.deepcopy(ledger)
            mutant = mutate(source_text)
            self.assertNotEqual(mutant, source_text)
            changed["fixture_corrections"][0]["files"][0]["after_blob"] = self.git_blob(mutant)
            variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(variant=index):
                self.assertTrue(self.exact_wms517_history_errors(changed))

    def git_blob(self, text):
        return subprocess.check_output(
            ["git", "hash-object", "--stdin"], input=text, text=True, cwd=REPOSITORY,
        ).strip()


if __name__ == "__main__":
    unittest.main()
