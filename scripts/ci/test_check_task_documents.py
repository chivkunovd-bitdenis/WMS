import importlib.util
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_task_documents", Path(__file__).with_name("check_task_documents.py")
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

EXACT_REVIEWED_CHAINS = json.loads(
    (Path(__file__).with_name("tests") / "fixtures" /
     "wms652_exact_reviewed_correction_chains.json").read_text(encoding="utf-8")
)["tasks"]

DOCUMENT = """# Задача

| Проверка | Требования | Вердикт |
| --- | --- | --- |
| Повторное нажатие | R1 | Нарушено: две записи |
| Возврат на экран | R1 | Подтверждено |

## Заключение
Нужно исправить повторное сохранение.
"""

CLASSIFIED_DOCUMENT = """# Задача

| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | backend/tests/test_contract.py::test_saved_result | Подтверждено |
| C2 | разово | backend/tests/test_contract.py::test_migration | Подтверждено |
| C3 | руками | | Подтверждено |

## Заключение
Принято.
"""


class DocumentTests(unittest.TestCase):
    def test_filled_failed_verdict_is_valid(self):
        self.assertEqual(checker.document_errors(DOCUMENT), [])

    def test_extra_columns_case_whitespace_and_aliases(self):
        doc = DOCUMENT.replace("Проверка", " **СЦЕНАРИЙ** ").replace("Вердикт", "результат проверки")
        doc = doc.replace("## Заключение", "## 7. Итоговое заключение")
        self.assertEqual(checker.document_errors(doc), [])

    def test_empty_verdict(self):
        errors = checker.document_errors(DOCUMENT.replace("Нарушено: две записи", " "))
        self.assertTrue(any("Нет вердикта" in error for error in errors))

    def test_missing_cell(self):
        errors = checker.document_errors(DOCUMENT.replace("| R1 | Нарушено: две записи |", "| R1 |"))
        self.assertTrue(any("число ячеек" in error for error in errors))

    def test_empty_table(self):
        doc = "| Проверка | Вердикт |\n| --- | --- |\n\n## Заключение\nПринято."
        self.assertTrue(any("Нет проверок" in error for error in checker.document_errors(doc)))

    def test_no_prose_checks(self):
        doc = "Проверка: всё работает. Вердикт: принято.\n## Заключение\nПринято."
        self.assertTrue(any("Нет проверок" in error for error in checker.document_errors(doc)))

    def test_fenced_example_is_not_evidence(self):
        self.assertTrue(checker.document_errors(f"```markdown\n{DOCUMENT}\n```"))

    def test_empty_conclusion_does_not_consume_next_section(self):
        doc = DOCUMENT.replace("Нужно исправить повторное сохранение.", "\n## Источники\nЗапрос владельца")
        self.assertIn("Не заполнен раздел «Заключение».", checker.document_errors(doc))

    def test_second_table_also_requires_verdicts(self):
        doc = DOCUMENT + "\n| Проверка | Вердикт |\n| --- | --- |\n| Ошибка API | |\n"
        self.assertTrue(any("Нет вердикта" in error for error in checker.document_errors(doc)))

    def test_escaped_pipe_in_description(self):
        self.assertEqual(checker.document_errors(DOCUMENT.replace("Повторное нажатие", r"Текст A\|B")), [])

    def test_missing_separator_is_actionable_error(self):
        errors = checker.document_errors(DOCUMENT.replace("| --- | --- | --- |", ""))
        self.assertTrue(any("разделителей" in error for error in errors))

    def test_classified_checks_resolve_test_file_and_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test = root / "backend/tests/test_contract.py"
            test.parent.mkdir(parents=True)
            test.write_text(
                "def test_saved_result(): pass\ndef test_migration(): pass\n",
                encoding="utf-8",
            )
            self.assertEqual(checker.document_errors(CLASSIFIED_DOCUMENT, root), [])

    def test_one_check_can_reference_several_tests_with_html_breaks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test = root / "backend/tests/test_contract.py"
            test.parent.mkdir(parents=True)
            test.write_text(
                "def test_saved_result(): pass\ndef test_second_guard(): pass\n"
                "def test_migration(): pass\n",
                encoding="utf-8",
            )
            doc = CLASSIFIED_DOCUMENT.replace(
                "backend/tests/test_contract.py::test_saved_result",
                "backend/tests/test_contract.py::test_saved_result"
                "<br>backend/tests/test_contract.py::test_second_guard",
            )
            self.assertEqual(checker.document_errors(doc, root), [])

    def test_automated_class_requires_test_reference(self):
        doc = CLASSIFIED_DOCUMENT.replace(
            "backend/tests/test_contract.py::test_saved_result", ""
        )
        errors = checker.document_errors(doc, Path("."))
        self.assertTrue(any("нет ссылки на тест" in error for error in errors))

    def test_test_reference_requires_existing_file_and_test_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test = root / "backend/tests/test_contract.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_other(): pass\n", encoding="utf-8")
            errors = checker.document_errors(CLASSIFIED_DOCUMENT, root)
            self.assertTrue(any("не найдено имя теста test_saved_result" in error for error in errors))
            missing = CLASSIFIED_DOCUMENT.replace("backend/tests/test_contract.py", "missing.py")
            errors = checker.document_errors(missing, root)
            self.assertTrue(any("нет файла теста missing.py" in error.casefold() for error in errors))


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write("AGENTS.md", "Правила\n")
        self.write("CLAUDE.md", "Правила\n")
        self.base = self.commit("WMS-001 legacy base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def rollout(self):
        self.write(checker.SCRIPT_PATH, "# rollout marker\n")
        self.write("docs/requirements/WMS-437.md", DOCUMENT)
        return self.commit("WMS-437 introduce document check")

    @staticmethod
    def current_integration_checker():
        integration = Path(__file__).resolve().parents[2].parent / "night1007-integration"
        path = integration / "scripts/ci/check_task_documents.py"
        # During this test-writer stage exercise the live integration candidate;
        # after the contract is merged, run the same tests against their local
        # checked-in checker rather than a worktree-specific absolute path.
        if not path.is_file():
            path = Path(__file__).with_name("check_task_documents.py")
        spec = importlib.util.spec_from_file_location(
            "current_integration_check_task_documents",
            path,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def protected_wms687_document_gate_fixture(self):
        source = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        inbound = "inbound selects only document products and opens the catalog FbsStockDialogContainer"
        returned = "return selects only document products and opens the catalog FbsStockDialogContainer"
        full_prefix = "WMS-687 shared FBS stock dialog from an inbound document"
        # These are actual test.each values, not literal source names.  A broad
        # describe/prefix match would incorrectly approve unrelated cases.
        self.write(source, """import { describe, it } from 'vitest'\n\ndescribe('WMS-687 shared FBS stock dialog from an inbound document', () => {\n  it.each(['inbound', 'return'])('%s selects only document products and opens the catalog FbsStockDialogContainer', () => {})\n})\n""")
        report = "frontend-all.json"
        cases = [f"src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx::{full_prefix} {name}"
                 for name in (inbound, returned)]
        self.write(report, json.dumps({
            "success": True,
            "testResults": [{
                "name": f"/workspace/frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx",
                "status": "passed",
                "assertionResults": [{"fullName": f"{full_prefix} {name}", "status": "passed"}
                                     for name in (inbound, returned)],
            }],
        }) + "\n")
        digest = hashlib.sha256((self.root / source).read_bytes()).hexdigest()
        policy = {
            "version": 1,
            "files": {source: digest},
            "suites": {"frontend-fbs": {
                "report": report, "format": "vitest", "exact": False, "cases": cases,
            }},
        }
        self.write("guards/PROCESS_CONTRACTS.json", json.dumps(policy) + "\n")
        self.commit("WMS-687: save protected expanded DOM contract")
        def document(name):
            return f"""# WMS-687\n\n| Проверка | Класс | Тест | Вердикт |\n| --- | --- | --- | --- |\n| C1 | навсегда | {source}::{name} | Подтверждено |\n\n## Заключение\nПринято.\n"""
        return source, inbound, returned, report, policy, document

    def immutable_blob(self, commit: str, path: str) -> str:
        """Read a published object, never the moving checkout version of a test."""
        project = Path(__file__).resolve().parents[2]
        return subprocess.check_output(
            ["git", "show", f"{commit}:{path}"], cwd=project, text=True,
        )

    @staticmethod
    def exact_transform(task_id: str, step: int, path: str) -> str:
        return f"{task_id.lower()}-reviewed-{step}-{path.rsplit('/', 1)[-1]}"

    def reviewed_exact_chain(self, task_id: str, *, tamper: str | None = None):
        """Build a small Git graph from immutable published blobs and metadata.

        Commit ids are deliberately synthetic; every source/correction content
        hash, exact path, report binding and graph edge comes from the published
        independent-review mapping.  That makes this a stable checker fixture,
        rather than a dependency on whatever HEAD happens to contain.
        """
        record = EXACT_REVIEWED_CHAINS[task_id]
        rollout = self.rollout()
        for path in record["frozen_files"]:
            self.write(path, self.immutable_blob(record["original_contract"], path))
        requirement = f"docs/requirements/{task_id}.md"
        first = record["steps"][0]
        if requirement in first.get("ancillary", {}):
            self.write(requirement, self.immutable_blob(first["source"], requirement))
        else:
            self.write(requirement, DOCUMENT)
        contract = self.commit(f"{task_id}: контракт тестов")

        entries = []
        source = contract
        for number, step in enumerate(record["steps"], 1):
            for path in step["files"]:
                self.write(path, self.immutable_blob(step["correction"], path))
            for path in step.get("ancillary", {}):
                self.write(path, self.immutable_blob(step["correction"], path))
            if tamper == "other-file" and number == 1:
                self.write("backend/app/unrelated.py", "must never enter a fixture correction\n")
            correction = self.commit(f"{task_id}: independently reviewed fixture correction {number}")
            evidence = f"docs/reviews/{task_id}-fixture-review-{number}.md"
            self.write(evidence, f"independent high PASS for {correction}\n")
            evidence_commit = self.commit(f"{task_id}: publish fixture review {number}")
            items = []
            for path, (before, after) in step["files"].items():
                items.append({
                    "transform": self.exact_transform(task_id, number, path),
                    "path": path, "before_blob": before, "after_blob": after,
                })
            review = {
                "model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS",
                "source_commit": source, "correction_commit": correction,
                "evidence": evidence, "evidence_commit": evidence_commit,
                "evidence_blob": checker.git_blob(self.root, evidence_commit, evidence),
            }
            entries.append({
                "contract_commit": contract, "source_commit": source,
                "correction_commit": correction, "files": items,
                "companion_files": [
                    {"path": path, "before_blob": before, "after_blob": after}
                    for path, (before, after) in step.get("ancillary", {}).items()
                ],
                "review": review,
            })
            # The next independently reviewed source is a real descendant which
            # did not alter the frozen bytes; rejecting it would erase the audit.
            source = evidence_commit
        ledger = {"task": task_id, "fixture_corrections": entries}
        if tamper == "wrong-source":
            ledger["fixture_corrections"][1]["source_commit"] = "f" * 40
        elif tamper == "wrong-blob":
            ledger["fixture_corrections"][0]["files"][0]["after_blob"] = "0" * 40
        elif tamper == "missing-review":
            ledger["fixture_corrections"][0]["review"].pop("model")
        elif tamper == "wrong-report":
            report = ledger["fixture_corrections"][0]["review"]["evidence"]
            self.write(report, "rewritten report\n")
            self.commit(f"{task_id}: mutate published review artifact")
        self.write(
            f"docs/reviews/contract-corrections/{task_id}.json",
            json.dumps(ledger, ensure_ascii=False) + "\n",
        )
        self.commit(f"{task_id}: store exact independently reviewed chain")
        return rollout

    def wms687_document(self, test_links: str) -> str:
        return f"""# WMS-687

| Проверка | Требование | Класс | Тест | Ожидаемый результат | Вердикт |
| --- | --- | --- | --- | --- | --- |
| C1 | R1 | навсегда | {test_links} | Общий диалог сохраняет только выбранные строки документа. | принято |

## Заключение
Принято.
"""

    def wms687_contract(self, *, second_frozen: bool = False):
        rollout = self.rollout()
        frozen = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        self.write(frozen, "export const frozenContract = 'original'\n")
        frozen_paths = [frozen]
        if second_frozen:
            second = "frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts"
            self.write(second, "export const frozenPermission = 'original'\n")
            frozen_paths.append(second)
        document = "docs/requirements/WMS-687.md"
        self.write(document, self.wms687_document(f"{frozen}::WMS-687 old DOM contract"))
        contract = self.commit("WMS-687: контракт тестов")
        return rollout, contract, frozen_paths, document

    def wms687_ledger(self, contract: str, correction: str, files: list[str]) -> None:
        self.write(
            "docs/reviews/contract-corrections/WMS-687.json",
            json.dumps(
                {
                    "task": "WMS-687",
                    "contract_commit": contract,
                    "correction_commit": correction,
                    "files": files,
                    "review": {
                        "model": "gpt-6.1-sol",
                        "effort": "high",
                        "verdict": "PASS",
                    },
                }
            ) + "\n",
        )
        self.commit("WMS-687 correction ledger")

    def test_pre_rollout_history_ignored_but_introduction_checked(self):
        self.commit("WMS-002 legacy without contract")
        self.rollout()
        self.assertEqual(checker.task_refs(self.root, self.base), ["WMS-437"])
        self.assertEqual(checker.check(self.root, self.base), [])

    def test_multiple_tasks_and_missing_document(self):
        self.rollout()
        self.write("docs/requirements/WMS-438.md", DOCUMENT)
        self.commit("WMS-438 and WMS-439")
        self.assertEqual(checker.task_refs(self.root, self.base), ["WMS-437", "WMS-438", "WMS-439"])
        errors = checker.check(self.root, self.base)
        self.assertEqual(len(errors), 1)
        self.assertIn("WMS-439: нет документа", errors[0])

    def test_base_after_rollout_checks_only_new_commits(self):
        rollout = self.rollout()
        self.write("docs/requirements/WMS-438.md", DOCUMENT)
        self.commit("WMS-438 implementation")
        self.assertEqual(checker.task_refs(self.root, rollout), ["WMS-438"])

    def test_old_task_referenced_again_needs_contract(self):
        self.rollout()
        self.commit("WMS-001 follow-up")
        self.assertTrue(any("WMS-001: нет документа" in error for error in checker.check(self.root, self.base)))

    def test_rules_mismatch(self):
        self.rollout()
        self.write("CLAUDE.md", "Другой процесс\n")
        self.assertTrue(any("одинаковые правила" in error for error in checker.check(self.root, self.base)))

    def test_uncommitted_checker_does_not_backfill_history(self):
        self.commit("WMS-002 legacy")
        self.write(checker.SCRIPT_PATH, "# not introduced yet\n")
        self.assertEqual(checker.task_refs(self.root, self.base), [])

    def test_contract_commit_files_cannot_change_later(self):
        rollout = self.rollout()
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-700: контракт тестов")
        self.write("unrelated.txt", "allowed\n")
        self.commit("WMS-700 implementation")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

        self.write("backend/tests/test_contract.py", "def test_contract(): assert False\n")
        self.commit("WMS-700 weaken contract")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertEqual(len(errors), 1)
        self.assertIn("изменён контракт тестов WMS-700 после его фиксации", errors[0])

    def test_reviewed_contract_correction_becomes_new_frozen_baseline(self):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): assert rendered_column('size')\n")
        contract = self.commit("WMS-710: контракт тестов")
        self.write(path, "def test_contract(): assert rendered_cell('size')\n")
        correction = self.commit("WMS-710: исправить ложную PDF-проверку контракта")
        ledger = {
            "task": "WMS-710",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": [path],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-710.json",
            json.dumps(ledger, ensure_ascii=False) + "\n",
        )
        self.commit("WMS-710: зафиксировать проверенную коррекцию контракта")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

        self.write(path, "def test_contract(): assert True\n")
        self.commit("WMS-710 weaken corrected contract")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertEqual(len(errors), 1)
        self.assertIn("изменён контракт тестов WMS-710", errors[0])

    def sol61_correction_errors(self, effort):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): assert old_check()\n")
        contract = self.commit("WMS-722: контракт тестов")
        self.write(path, "def test_contract(): assert corrected_check()\n")
        correction = self.commit("WMS-722: correction")
        ledger = {
            "task": "WMS-722", "contract_commit": contract,
            "correction_commit": correction, "files": [path],
            "review": {"model": "gpt-6.1-sol", "effort": effort, "verdict": "PASS"},
        }
        self.write("docs/reviews/contract-corrections/WMS-722.json", json.dumps(ledger) + "\n")
        self.commit("WMS-722: correction ledger")
        return checker.contract_change_errors(self.root, rollout)

    def test_sol61_high_review_accepts_corrected_contract(self):
        self.assertEqual(self.sol61_correction_errors("high"), [])

    def test_sol61_low_review_cannot_accept_corrected_contract(self):
        self.assertTrue(any("реестр коррекции" in error
                            for error in self.sol61_correction_errors("low")))

    def disjoint_corrections(self):
        rollout = self.rollout()
        paths = [f"frontend/test_{name}.ts" for name in ("dom", "scope", "atomicity")]
        for path in paths:
            self.write(path, "assert original_check()\n")
        contract = self.commit("WMS-723: контракт тестов")
        entries = []
        for path in paths[:2]:
            self.write(path, "assert corrected_check()\n")
            correction = self.commit("WMS-723: correct one test")
            entries.append({
                "contract_commit": contract, "correction_commit": correction,
                "files": [path],
                "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
            })
        return rollout, paths, contract, entries

    def save_corrections(self, entries, **extra):
        ledger = {"task": "WMS-723", "corrections": entries, **extra}
        self.write("docs/reviews/contract-corrections/WMS-723.json", json.dumps(ledger) + "\n")
        self.commit("WMS-723: correction ledger")

    def test_two_disjoint_corrections_keep_independent_frozen_baselines(self):
        rollout, _, _, entries = self.disjoint_corrections()
        self.save_corrections(entries)
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_array_corrections_reject_overlapping_files(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        self.write(paths[0], "assert another_correction()\n")
        entries.append({**entries[0], "correction_commit": self.commit("WMS-723: second DOM correction")})
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("пересекаются" in error for error in errors), errors)

    def test_array_corrections_reject_low_effort_review(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["review"]["effort"] = "low"
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

    def test_array_corrections_accept_sol_high_review(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["review"]["model"] = "gpt-6.1-sol"
        self.save_corrections(entries)
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_array_corrections_reject_unknown_model(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["review"]["model"] = "unknown-reviewer"
        self.save_corrections(entries)
        self.assertTrue(checker.contract_change_errors(self.root, rollout))

    def test_array_corrections_reject_non_pass_review(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["review"]["verdict"] = "FAIL"
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

    def test_array_corrections_reject_unknown_original_contract(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["contract_commit"] = "f" * 40
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("неизвестный исходный контракт" in error for error in errors), errors)

    def test_array_corrections_reject_non_contract_ancestor(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["contract_commit"] = rollout
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("неизвестный исходный контракт" in error for error in errors), errors)

    def test_array_corrections_reject_extra_file_in_correction_commit(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        self.write(paths[1], "assert reviewed_scope_check()\n")
        self.write("frontend/product.ts", "unapproved_product_change()\n")
        entries[1]["correction_commit"] = self.commit("WMS-723: correction plus product change")
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("ровно перечисленные файлы" in error for error in errors), errors)

    def test_array_corrections_reject_non_frozen_file(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["files"] = ["frontend/product.ts"]
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("только часть исходного контракта" in error for error in errors), errors)

    def test_array_corrections_do_not_absorb_later_mutation_of_first_file(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        self.write(paths[0], "assert True\n")
        self.commit("WMS-723: weaken first corrected file")
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any(paths[0] in error for error in errors), errors)

    def test_array_corrections_preserve_untouched_original_file(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        self.write(paths[2], "assert True\n")
        self.commit("WMS-723: weaken untouched test")
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any(paths[2] in error for error in errors), errors)

    def test_array_corrections_reject_wholesale_replacement_in_one_commit(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        for path in paths:
            self.write(path, "assert all_new_checks()\n")
        entries = [{**entries[0], "files": paths,
                    "correction_commit": self.commit("WMS-723: replace entire contract")}]
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("только часть исходного контракта" in error for error in errors), errors)

    def test_array_corrections_reject_original_commit_as_correction(self):
        rollout, _, contract, entries = self.disjoint_corrections()
        entries[1]["correction_commit"] = contract
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("отдельным последующим коммитом" in error for error in errors), errors)

    def test_array_corrections_reject_correction_outside_head_history(self):
        rollout, paths, contract, entries = self.disjoint_corrections()
        branch = self.git("branch", "--show-current")
        self.git("checkout", "-q", "-b", "detached-correction", contract)
        self.write(paths[1], "assert divergent_correction()\n")
        entries[1]["correction_commit"] = self.commit("WMS-723: divergent correction")
        self.git("checkout", "-q", branch)
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("отсутствует в текущей версии" in error for error in errors), errors)

    def test_array_corrections_reject_empty_array(self):
        rollout, _, _, _ = self.disjoint_corrections()
        self.save_corrections([])
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

    def test_array_corrections_reject_non_object_entry(self):
        rollout, _, _, entries = self.disjoint_corrections()
        self.save_corrections([entries[0], "invalid"])
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

    def test_array_corrections_reject_ambiguous_legacy_fields(self):
        rollout, _, contract, entries = self.disjoint_corrections()
        self.save_corrections(entries, contract_commit=contract)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

    def test_array_corrections_require_strict_subset_even_for_single_file_contract(self):
        rollout = self.rollout()
        path = "frontend/test_dom.ts"
        self.write(path, "assert original_check()\n")
        contract = self.commit("WMS-723: контракт тестов")
        self.write(path, "assert corrected_check()\n")
        correction = self.commit("WMS-723: correct only contract file")
        self.save_corrections([{
            "contract_commit": contract, "correction_commit": correction, "files": [path],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }])
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("только часть исходного контракта" in error for error in errors), errors)

    def test_array_corrections_validate_entries_for_contract_before_base(self):
        rollout, paths, _, entries = self.disjoint_corrections()
        self.save_corrections(entries)
        later_base = self.git("rev-parse", "HEAD")
        self.write("frontend/test_later.ts", "assert later_check()\n")
        self.commit("WMS-723: контракт тестов")
        self.assertEqual(checker.contract_change_errors(self.root, later_base), [])
        entries[0]["files"] = [paths[2]]
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, later_base)
        self.assertTrue(any("ровно перечисленные файлы" in error for error in errors), errors)

    def test_contract_correction_ledger_rejects_unreviewed_or_extra_files(self):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): pass\n")
        contract = self.commit("WMS-711: контракт тестов")
        self.write(path, "def test_contract(): assert True\n")
        correction = self.commit("WMS-711: correction")
        ledger = {
            "task": "WMS-711",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": [path, "app.py"],
            "review": {"model": "gpt-6-astra", "effort": "medium", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-711.json",
            json.dumps(ledger) + "\n",
        )
        self.commit("WMS-711 invalid correction ledger")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("реестр коррекции" in error for error in errors))

    def test_contract_correction_rejects_extra_file_with_valid_review(self):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): pass\n")
        contract = self.commit("WMS-715: контракт тестов")
        self.write(path, "def test_contract(): assert True\n")
        correction = self.commit("WMS-715: correction")
        ledger = {
            "task": "WMS-715",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": [path, "app.py"],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-715.json",
            json.dumps(ledger) + "\n",
        )
        self.commit("WMS-715 invalid file list")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("только часть исходного контракта" in error for error in errors))

    def test_non_object_contract_correction_ledger_is_actionable_error(self):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): pass\n")
        self.commit("WMS-716: контракт тестов")
        self.write(
            "docs/reviews/contract-corrections/WMS-716.json",
            "[]\n",
        )
        self.commit("WMS-716 invalid ledger type")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("JSON-объектом" in error for error in errors))

    def test_correction_targets_one_of_several_contract_commits_for_same_task(self):
        rollout = self.rollout()
        first = "backend/tests/test_first.py"
        second = "backend/tests/test_second.py"
        self.write(first, "def test_first(): assert column_text()\n")
        first_contract = self.commit("WMS-717: контракт тестов")
        self.write(second, "def test_second(): assert rollback()\n")
        self.commit("WMS-717: контракт тестов")
        self.write(first, "def test_first(): assert cell_text()\n")
        correction = self.commit("WMS-717: correct first contract")
        ledger = {
            "task": "WMS-717",
            "contract_commit": first_contract,
            "correction_commit": correction,
            "files": [first],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-717.json",
            json.dumps(ledger) + "\n",
        )
        self.commit("WMS-717 correction ledger")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_prior_reviewed_contract_does_not_block_later_contract_for_same_task(self):
        rollout = self.rollout()
        task = "WMS-721"
        first = "backend/tests/test_first.py"
        second = "backend/tests/test_second.py"
        self.write(first, "def test_first(): assert column_text()\n")
        first_contract = self.commit(f"{task}: контракт тестов")
        self.write(first, "def test_first(): assert cell_text()\n")
        correction = self.commit(f"{task}: correct first contract")
        ledger = {
            "task": task,
            "contract_commit": first_contract,
            "correction_commit": correction,
            "files": [first],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            f"docs/reviews/contract-corrections/{task}.json",
            json.dumps(ledger) + "\n",
        )
        self.commit(f"{task} correction ledger")
        later_rollout = self.git("rev-parse", "HEAD")
        self.write(second, "def test_second(): assert rollback()\n")
        self.commit(f"{task}: контракт тестов")
        self.assertEqual(checker.contract_change_errors(self.root, later_rollout), [])
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_correction_ledger_rejects_missing_or_unknown_contract_commit(self):
        for task, ledger_contract, expected in (
            ("WMS-718", None, "заполнен не полностью"),
            ("WMS-719", "f" * 40, "неизвестный исходный контракт"),
        ):
            with self.subTest(task=task):
                rollout = self.rollout()
                path = f"backend/tests/test_{task.casefold()}.py"
                self.write(path, "def test_contract(): pass\n")
                contract = self.commit(f"{task}: контракт тестов")
                ledger = {
                    "task": task,
                    "contract_commit": ledger_contract,
                    "correction_commit": contract,
                    "files": [path],
                    "review": {
                        "model": "gpt-6-astra",
                        "effort": "high",
                        "verdict": "PASS",
                    },
                }
                self.write(
                    f"docs/reviews/contract-corrections/{task}.json",
                    json.dumps(ledger) + "\n",
                )
                self.commit(f"{task} invalid source contract")
                errors = checker.contract_change_errors(self.root, rollout)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_correction_must_be_a_strictly_later_commit(self):
        rollout = self.rollout()
        task = "WMS-720"
        path = "backend/tests/test_same_commit.py"
        self.write(path, "def test_contract(): pass\n")
        contract = self.commit(f"{task}: контракт тестов")
        ledger = {
            "task": task,
            "contract_commit": contract,
            "correction_commit": contract,
            "files": [path],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            f"docs/reviews/contract-corrections/{task}.json",
            json.dumps(ledger) + "\n",
        )
        self.commit(f"{task} invalid same-commit correction")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("отдельным последующим коммитом" in error for error in errors), errors)

    def test_uncommitted_contract_correction_ledger_is_ignored(self):
        rollout = self.rollout()
        path = "backend/tests/test_contract.py"
        self.write(path, "def test_contract(): pass\n")
        contract = self.commit("WMS-713: контракт тестов")
        self.write(path, "def test_contract(): assert True\n")
        correction = self.commit("WMS-713: correction")
        ledger = {
            "task": "WMS-713",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": [path],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-713.json",
            json.dumps(ledger) + "\n",
        )
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertEqual(len(errors), 1)
        self.assertIn("изменён контракт тестов WMS-713", errors[0])

    def test_correction_cannot_replace_a_multi_file_contract_wholesale(self):
        rollout = self.rollout()
        paths = ["backend/tests/test_a.py", "backend/tests/test_b.py"]
        for path in paths:
            self.write(path, "def test_contract(): pass\n")
        contract = self.commit("WMS-714: контракт тестов")
        for path in paths:
            self.write(path, "def test_contract(): assert True\n")
        correction = self.commit("WMS-714: replace all contract files")
        ledger = {
            "task": "WMS-714",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": paths,
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-714.json",
            json.dumps(ledger) + "\n",
        )
        self.commit("WMS-714 correction ledger")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("только часть исходного контракта" in error for error in errors))

    def test_correction_does_not_absorb_an_earlier_change_to_another_frozen_file(self):
        rollout = self.rollout()
        corrected = "backend/tests/test_pdf.py"
        untouched = "backend/tests/test_atomicity.py"
        self.write(corrected, "def test_pdf(): assert column_text()\n")
        self.write(untouched, "def test_atomicity(): assert rollback()\n")
        contract = self.commit("WMS-712: контракт тестов")
        self.write(untouched, "def test_atomicity(): assert True\n")
        self.commit("WMS-712 weaken unrelated frozen test")
        self.write(corrected, "def test_pdf(): assert cell_text()\n")
        correction = self.commit("WMS-712: исправить PDF-проверку контракта")
        ledger = {
            "task": "WMS-712",
            "contract_commit": contract,
            "correction_commit": correction,
            "files": [corrected],
            "review": {"model": "gpt-6-astra", "effort": "high", "verdict": "PASS"},
        }
        self.write(
            "docs/reviews/contract-corrections/WMS-712.json",
            json.dumps(ledger) + "\n",
        )
        self.commit("WMS-712 correction ledger")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertEqual(len(errors), 1)
        self.assertIn(untouched, errors[0])

    def test_similarly_named_commit_does_not_freeze_files(self):
        rollout = self.rollout()
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-701: контракт тестов draft")
        self.write("backend/tests/test_contract.py", "def test_contract(): assert True\n")
        self.commit("WMS-701 implementation")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_pull_request_merge_commit_is_not_a_contract_change(self):
        # На pull_request CI проверяет служебный merge-коммит PR в базу: его diff
        # к первому родителю содержит весь PR, включая файлы контракта.
        rollout = self.rollout()
        trunk = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "feature")
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-703: контракт тестов")
        self.write("app.py", "implementation\n")
        self.commit("WMS-703 implementation")
        self.git("checkout", "-q", trunk)
        self.write("other.txt", "trunk moved on\n")
        self.commit("WMS-704 unrelated")
        self.git("merge", "-q", "--no-ff", "--no-edit", "feature")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_merging_base_into_branch_after_contract_is_allowed(self):
        rollout = self.rollout()
        trunk = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "feature")
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-705: контракт тестов")
        self.git("checkout", "-q", trunk)
        self.write("other.txt", "trunk moved on\n")
        self.commit("WMS-706 unrelated")
        self.git("checkout", "-q", "feature")
        self.git("merge", "-q", "--no-ff", "--no-edit", trunk)
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_merge_commit_that_edits_contract_is_still_a_change(self):
        rollout = self.rollout()
        trunk = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "feature")
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-707: контракт тестов")
        self.git("checkout", "-q", trunk)
        self.write("other.txt", "trunk moved on\n")
        self.commit("WMS-708 unrelated")
        self.git("checkout", "-q", "feature")
        self.git("merge", "-q", "--no-ff", "--no-commit", trunk)
        self.write("backend/tests/test_contract.py", "def test_contract(): assert False\n")
        self.git("add", ".")
        self.git("commit", "-q", "--no-edit")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertEqual(len(errors), 1)
        self.assertIn("backend/tests/test_contract.py", errors[0])

    def test_acceptance_verdicts_in_requirements_after_contract_are_allowed(self):
        rollout = self.rollout()
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.write("docs/requirements/WMS-709.md", "| Проверка | Тест | Вердикт |\n")
        self.commit("WMS-709: контракт тестов")
        self.write("docs/requirements/WMS-709.md", "| Проверка | Тест | Вердикт |\n| C1 | x | Подтверждено |\n")
        self.commit("WMS-709 acceptance")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_renaming_frozen_contract_file_is_a_change(self):
        rollout = self.rollout()
        self.write("backend/tests/test_contract.py", "def test_contract(): pass\n")
        self.commit("WMS-702: контракт тестов")
        self.git("mv", "backend/tests/test_contract.py", "backend/tests/test_renamed.py")
        self.commit("WMS-702 rename contract")
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("WMS-702" in error for error in errors))

    def test_protected_wms687_expanded_inbound_reference_uses_exact_receipt_case(self):
        _, inbound, _, _, _, document = self.protected_wms687_document_gate_fixture()
        errors = self.current_integration_checker().document_errors(document(inbound), self.root)
        self.assertEqual(errors, [])

    def test_protected_wms687_expanded_return_reference_uses_exact_receipt_case(self):
        _, _, returned, _, _, document = self.protected_wms687_document_gate_fixture()
        errors = self.current_integration_checker().document_errors(document(returned), self.root)
        self.assertEqual(errors, [])

    def test_protected_wms687_expanded_reference_rejects_unbound_or_changed_proof(self):
        for tamper in ("changed-head", "dirty", "missing-case", "wrong-report", "unregistered"):
            with self.subTest(tamper=tamper):
                with tempfile.TemporaryDirectory() as directory:
                    isolated = self.__class__()
                    isolated.temp = tempfile.TemporaryDirectory(dir=directory)
                    isolated.root = Path(isolated.temp.name)
                    isolated.git("init", "-q")
                    isolated.git("config", "user.name", "Fixture")
                    isolated.git("config", "user.email", "fixture@example.invalid")
                    isolated.write("AGENTS.md", "Rules\n")
                    isolated.write("CLAUDE.md", "Rules\n")
                    isolated.base = isolated.commit("WMS-001 legacy base")
                    try:
                        source, _, returned, _, policy, document = isolated.protected_wms687_document_gate_fixture()
                        if tamper == "changed-head":
                            isolated.write(source, "it('changed protected original', () => {})\n")
                            isolated.commit("WMS-687: changed protected original")
                        elif tamper == "dirty":
                            isolated.write(source, (isolated.root / source).read_text() + "// dirty\n")
                        else:
                            if tamper == "missing-case":
                                policy["suites"]["frontend-fbs"]["cases"] = [
                                    policy["suites"]["frontend-fbs"]["cases"][0]
                                ]
                            elif tamper == "wrong-report":
                                policy["suites"]["frontend-fbs"]["report"] = "other-frontend.json"
                                isolated.write("other-frontend.json", "{}\n")
                            elif tamper == "unregistered":
                                policy["files"] = {}
                            isolated.write("guards/PROCESS_CONTRACTS.json", json.dumps(policy) + "\n")
                            isolated.commit(f"WMS-687: {tamper} protected proof")
                        errors = isolated.current_integration_checker().document_errors(document(returned), isolated.root)
                        self.assertTrue(errors, errors)
                    finally:
                        isolated.temp.cleanup()

    def test_unprotected_legacy_test_reference_stays_literal(self):
        source = "frontend/src/screens/ff/Legacy.test.tsx"
        self.write(source, "it('legacy literal case', () => {})\n")
        document = f"""# Legacy

| Проверка | Класс | Тест | Вердикт |
| --- | --- | --- | --- |
| C1 | навсегда | {source}::legacy literal case | Подтверждено |

## Заключение
Принято.
"""
        self.assertEqual(self.current_integration_checker().document_errors(document, self.root), [])

    def test_wms687_reviewed_correction_allows_only_new_task_tests_and_own_test_links(self):
        rollout, contract, [frozen], document = self.wms687_contract()
        regression = "frontend/src/screens/ff/FfInboundRequestView.wms687.regression.dom.test.tsx"
        permission = "frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts"
        self.write(frozen, "export const frozenContract = 'reviewed correction'\n")
        self.write(regression, "export const regression = 'WMS-687'\n")
        self.write(permission, "export const permission = 'WMS-687'\n")
        self.write(
            document,
            self.wms687_document(
                f"{frozen}::WMS-687 old DOM contract<br>"
                f"{regression}::WMS-687 shared dialog regression<br>"
                f"{permission}::WMS-687 catalog permission wiring"
            ),
        )
        correction = self.commit("WMS-687: correction after independent review")
        self.wms687_ledger(contract, correction, [frozen])

        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_wms687_correction_rejects_product_or_other_task_test_companion(self):
        for path in (
            "frontend/src/screens/ff/FfInboundRequestView.tsx",
            "frontend/src/screens/ff/FfInboundRequestView.wms688.regression.dom.test.tsx",
        ):
            with self.subTest(path=path):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    subprocess.check_call(["git", "init", "-q"], cwd=root)
                    subprocess.check_call(["git", "config", "user.name", "Fixture"], cwd=root)
                    subprocess.check_call(["git", "config", "user.email", "fixture@example.invalid"], cwd=root)
                    (root / "AGENTS.md").write_text("Rules\n")
                    (root / "CLAUDE.md").write_text("Rules\n")
                    def write(name, text):
                        target = root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text)
                    def commit(message):
                        subprocess.check_call(["git", "add", "."], cwd=root)
                        subprocess.check_call(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=root)
                        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
                    write(checker.SCRIPT_PATH, "# rollout marker\n")
                    rollout = commit("WMS-437 introduce document check")
                    frozen = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
                    write(frozen, "export const frozenContract = 'original'\n")
                    write("docs/requirements/WMS-687.md", self.wms687_document(f"{frozen}::old"))
                    contract = commit("WMS-687: контракт тестов")
                    write(frozen, "export const frozenContract = 'reviewed correction'\n")
                    write(path, "export const unrelated = true\n")
                    correction = commit("WMS-687 correction with forbidden companion")
                    write(
                        "docs/reviews/contract-corrections/WMS-687.json",
                        json.dumps({
                            "task": "WMS-687", "contract_commit": contract,
                            "correction_commit": correction, "files": [frozen],
                            "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS"},
                        }) + "\n",
                    )
                    commit("WMS-687 correction ledger")
                    self.assertTrue(checker.contract_change_errors(root, rollout))

    def test_wms687_correction_rejects_foreign_or_semantic_requirement_change(self):
        for changed_document, before, replacement in (
            ("docs/requirements/WMS-688.md", "", "foreign requirement\n"),
            ("docs/requirements/WMS-687.md", "R1", "R99"),
            ("docs/requirements/WMS-687.md", "Общий диалог сохраняет только выбранные строки документа.",
             "Общий диалог меняет бизнес-результат."),
        ):
            with self.subTest(document=changed_document):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    subprocess.check_call(["git", "init", "-q"], cwd=root)
                    subprocess.check_call(["git", "config", "user.name", "Fixture"], cwd=root)
                    subprocess.check_call(["git", "config", "user.email", "fixture@example.invalid"], cwd=root)
                    def write(name, text):
                        target = root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text)
                    def commit(message):
                        subprocess.check_call(["git", "add", "."], cwd=root)
                        subprocess.check_call(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=root)
                        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
                    write("AGENTS.md", "Rules\n")
                    write("CLAUDE.md", "Rules\n")
                    write(checker.SCRIPT_PATH, "# rollout marker\n")
                    rollout = commit("WMS-437 introduce document check")
                    frozen = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
                    write(frozen, "export const frozenContract = 'original'\n")
                    original_doc = self.wms687_document(f"{frozen}::old")
                    write("docs/requirements/WMS-687.md", original_doc)
                    write("docs/requirements/WMS-688.md", "# WMS-688\n")
                    contract = commit("WMS-687: контракт тестов")
                    write(frozen, "export const frozenContract = 'reviewed correction'\n")
                    if changed_document.endswith("WMS-687.md"):
                        write(changed_document, original_doc.replace(before, replacement))
                    else:
                        write(changed_document, replacement)
                    correction = commit("WMS-687 correction with forbidden requirement edit")
                    write(
                        "docs/reviews/contract-corrections/WMS-687.json",
                        json.dumps({
                            "task": "WMS-687", "contract_commit": contract,
                            "correction_commit": correction, "files": [frozen],
                            "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS"},
                        }) + "\n",
                    )
                    commit("WMS-687 correction ledger")
                    self.assertTrue(checker.contract_change_errors(root, rollout))

    def test_wms687_correction_rejects_undeclared_or_deleted_frozen_test(self):
        for mode in ("undeclared", "deleted"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    subprocess.check_call(["git", "init", "-q"], cwd=root)
                    subprocess.check_call(["git", "config", "user.name", "Fixture"], cwd=root)
                    subprocess.check_call(["git", "config", "user.email", "fixture@example.invalid"], cwd=root)
                    def write(name, text):
                        target = root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text)
                    def commit(message):
                        subprocess.check_call(["git", "add", "."], cwd=root)
                        subprocess.check_call(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=root)
                        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
                    write("AGENTS.md", "Rules\n")
                    write("CLAUDE.md", "Rules\n")
                    write(checker.SCRIPT_PATH, "# rollout marker\n")
                    rollout = commit("WMS-437 introduce document check")
                    frozen = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
                    second = "frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts"
                    write(frozen, "export const frozenContract = 'original'\n")
                    write(second, "export const frozenPermission = 'original'\n")
                    write("docs/requirements/WMS-687.md", self.wms687_document(f"{frozen}::old"))
                    contract = commit("WMS-687: контракт тестов")
                    if mode == "deleted":
                        subprocess.check_call(["git", "rm", "-q", frozen], cwd=root)
                    else:
                        write(frozen, "export const frozenContract = 'reviewed correction'\n")
                        write(second, "export const frozenPermission = 'changed outside ledger'\n")
                    correction = commit("WMS-687 correction with invalid frozen scope")
                    write(
                        "docs/reviews/contract-corrections/WMS-687.json",
                        json.dumps({
                            "task": "WMS-687", "contract_commit": contract,
                            "correction_commit": correction, "files": [frozen],
                            "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS"},
                        }) + "\n",
                    )
                    commit("WMS-687 correction ledger")
                    self.assertTrue(checker.contract_change_errors(root, rollout))

    def test_wms658_published_exact_chain_with_own_test_links_is_accepted(self):
        """658 has one reviewed requirements-Test-links companion, no broad companion rule."""
        rollout = self.reviewed_exact_chain("WMS-658")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_wms681_published_two_by_two_exact_chain_is_accepted(self):
        """Both frozen 681 files change in each of its two approved corrections."""
        rollout = self.reviewed_exact_chain("WMS-681")
        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_reviewed_658_and_681_exact_chain_rejects_every_binding_canary(self):
        # These are not a generic migration escape hatch: each kind of binding
        # failure must stay fatal after the two positive chains are implemented.
        for task_id, tamper in (
            ("WMS-658", "wrong-source"),
            ("WMS-658", "wrong-blob"),
            ("WMS-658", "other-file"),
            ("WMS-681", "missing-review"),
            ("WMS-681", "wrong-report"),
        ):
            with self.subTest(task_id=task_id, tamper=tamper):
                with tempfile.TemporaryDirectory() as directory:
                    isolated = self.__class__()
                    # Reuse the normal fixture setup on an independent Git repo;
                    # no case shares chain state or a mutable evidence artifact.
                    isolated.temp = tempfile.TemporaryDirectory(dir=directory)
                    isolated.root = Path(isolated.temp.name)
                    isolated.git("init", "-q")
                    isolated.git("config", "user.name", "Fixture")
                    isolated.git("config", "user.email", "fixture@example.invalid")
                    isolated.write("AGENTS.md", "Rules\n")
                    isolated.write("CLAUDE.md", "Rules\n")
                    isolated.base = isolated.commit("WMS-001 legacy base")
                    try:
                        rollout = isolated.reviewed_exact_chain(task_id, tamper=tamper)
                        self.assertTrue(checker.contract_change_errors(isolated.root, rollout))
                    finally:
                        isolated.temp.cleanup()

    def test_exact_chain_records_pin_the_two_published_review_artifacts(self):
        # The fixture is an immutable source of real source/final/report/blob
        # values for the two ordinary fixture-only chains.
        for task_id, report_commit, report_blob in (
            ("WMS-658", "0d9d7cc735bf7506de0067991ff1b92e6b468a52",
             "0a48a0167af6e83b156ff003b66a842df09c42c6"),
            ("WMS-681", "4c3c53bb1a4057da7e003e024680c842c05abdc1",
             "fc539ecf01b0d652920d4f9a26b913e519eacaf9"),
        ):
            with self.subTest(task_id=task_id):
                report = EXACT_REVIEWED_CHAINS[task_id]["report"]
                self.assertEqual(report["commit"], report_commit)
                self.assertEqual(report["blob"], report_blob)
                self.assertEqual(len(EXACT_REVIEWED_CHAINS[task_id]["steps"]), 4 if task_id == "WMS-658" else 2)

    def test_exact_chain_records_match_published_parent_blobs_and_report(self):
        # This verifies the actual immutable objects separately from the small
        # synthetic graphs above.  It is intentionally independent of HEAD.
        project = Path(__file__).resolve().parents[2]
        for task_id in ("WMS-658", "WMS-681"):
            record = EXACT_REVIEWED_CHAINS[task_id]
            with self.subTest(task_id=task_id):
                self.assertTrue(checker.ancestor(project, record["original_contract"], record["final_correction_commit"]))
                report = record["report"]
                self.assertEqual(checker.git_blob(project, report["commit"], report["path"]), report["blob"])
                for step in record["steps"]:
                    parent = checker.git(project, "rev-list", "--parents", "-n", "1", step["correction"]).split()[1]
                    self.assertEqual(parent, step["source"])
                    for path, (before, after) in step["files"].items():
                        self.assertEqual(checker.git_blob(project, step["source"], path), before)
                        self.assertEqual(checker.git_blob(project, step["correction"], path), after)
                    for path, (before, after) in step.get("ancillary", {}).items():
                        self.assertEqual(checker.git_blob(project, step["source"], path), before)
                        self.assertEqual(checker.git_blob(project, step["correction"], path), after)

    def test_wms680_owner_semantic_and_fixture_matrix_is_registered_exactly(self):
        """680 is a closed owner supersession followed by four reviewed pairs."""
        record = EXACT_REVIEWED_CHAINS["WMS-680"]
        pairs = set(checker.FIXTURE_BLOB_PAIRS.values())
        missing = []
        for step in record["steps"]:
            if "transform" not in step:
                continue
            for path, (before, after) in step["files"].items():
                expected = ("WMS-680", path, before, after)
                if expected not in pairs:
                    missing.append((step["transform"], expected))
        # The owner record is deliberately separate from a fixture pair: it
        # binds only the published 3be84 evidence and 5739 semantic contract.
        if "WMS-680" not in checker.OWNER_UI_SUPERSESSIONS:
            missing.insert(0, ("owner-ui-supersession", "WMS-680"))
        self.assertEqual(missing, [])

    def test_wms680_manifest_matches_owner_evidence_all_frontiers_and_report(self):
        """Every allowed 680 edge is proved against immutable published Git data."""
        record = EXACT_REVIEWED_CHAINS["WMS-680"]
        project = Path(__file__).resolve().parents[2]
        owner = record["owner"]
        self.assertEqual(
            checker.git(project, "rev-list", "--parents", "-n", "1", owner["correction"]).split()[1],
            owner["source"],
        )
        for path, (before, after) in owner["artifacts"].items():
            self.assertEqual(checker.git_blob(project, owner["source"], path), before)
            self.assertEqual(checker.git_blob(project, owner["correction"], path), after)
        report = record["report"]
        self.assertEqual(checker.git_blob(project, report["commit"], report["path"]), report["blob"])
        self.assertTrue(checker.ancestor(project, owner["correction"], report["commit"]))
        for contract, paths in record["contracts"].items():
            self.assertEqual(checker.git(project, "show", "-s", "--format=%s", contract), "WMS-680: контракт тестов")
            self.assertTrue(checker.ancestor(project, contract, report["commit"]))
            for path, (before, after) in paths.items():
                self.assertEqual(checker.git_blob(project, contract, path), before)
                self.assertEqual(checker.git_blob(project, record["final_correction_commit"], path), after)
        for step in record["steps"]:
            parent = checker.git(project, "rev-list", "--parents", "-n", "1", step["correction"]).split()[1]
            self.assertEqual(parent, step.get("parent", step["source"]))
            for path, (before, after) in step["files"].items():
                self.assertEqual(checker.git_blob(project, step["source"], path), before)
                self.assertEqual(checker.git_blob(project, step["correction"], path), after)

    def test_wms680_closed_matrix_rejects_owner_report_assertion_and_scope_canaries(self):
        record = EXACT_REVIEWED_CHAINS["WMS-680"]
        pairs = set(checker.FIXTURE_BLOB_PAIRS.values())
        owner = record["owner"]
        contract_path = "frontend/src/utils/wms680PrintContract.test.ts"
        fixture = record["steps"][1]
        # A future registration may contain only the listed exact tuples.  Each
        # mutation below must therefore remain absent even after the positive
        # matrix becomes available.
        forbidden = {
            ("WMS-680", contract_path, "0" * 40, fixture["files"][contract_path][1]),
            ("WMS-680", contract_path, fixture["files"][contract_path][0], "0" * 40),
            ("WMS-680", "frontend/src/utils/unrelated.test.ts", "0" * 40, "1" * 40),
        }
        self.assertTrue(forbidden.isdisjoint(pairs))
        self.assertNotEqual(owner["artifacts"]["docs/requirements/WMS-680.md"][1], "0" * 40)
        self.assertNotEqual(record["report"]["blob"], "0" * 40)
        self.assertEqual(record["steps"][-1]["model"], "gpt-6.1-sol")
        self.assertEqual(record["steps"][-1]["effort"], "high")
    def test_legacy_wms654_exact_files_ledger_keeps_accepted_report_without_report_commit(self):
        rollout = self.rollout()
        report = "docs/reviews/WMS-654-correction-review.md"
        frozen = "frontend/src/sections/CatalogSection.wms654.test.tsx"
        self.write(report, "# Legacy WMS-654 independent PASS report\n")
        self.commit("WMS-654 independent review report")
        self.write(frozen, "export const frozenContract = 'original'\n")
        contract = self.commit("WMS-654: контракт тестов")
        self.write(frozen, "export const frozenContract = 'reviewed correction'\n")
        correction = self.commit("WMS-654 exact reviewed correction")
        self.write(
            "docs/reviews/contract-corrections/WMS-654.json",
            json.dumps(
                {
                    "task": "WMS-654",
                    "contract_commit": contract,
                    "correction_commit": correction,
                    "files": [frozen],
                    "review": {
                        "model": "gpt-6-astra",
                        "effort": "high",
                        "verdict": "PASS",
                        "report": report,
                    },
                }
            ) + "\n",
        )
        self.commit("WMS-654 correction ledger")

        self.assertEqual(checker.contract_change_errors(self.root, rollout), [])

    def test_wms687_ancillary_correction_with_report_still_requires_report_commit(self):
        rollout = self.rollout()
        report = "docs/reviews/WMS-687-correction-review.md"
        frozen = "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"
        regression = "frontend/src/screens/ff/FfInboundRequestView.wms687.regression.dom.test.tsx"
        self.write(report, "# WMS-687 independent PASS report\n")
        self.commit("WMS-687 independent review report")
        self.write(frozen, "export const frozenContract = 'original'\n")
        self.write("docs/requirements/WMS-687.md", self.wms687_document(f"{frozen}::old"))
        contract = self.commit("WMS-687: контракт тестов")
        self.write(frozen, "export const frozenContract = 'reviewed correction'\n")
        self.write(regression, "export const regression = 'WMS-687'\n")
        self.write(
            "docs/requirements/WMS-687.md",
            self.wms687_document(f"{frozen}::old<br>{regression}::WMS-687 regression"),
        )
        correction = self.commit("WMS-687 reviewed correction with ancillary test")
        self.write(
            "docs/reviews/contract-corrections/WMS-687.json",
            json.dumps(
                {
                    "task": "WMS-687",
                    "contract_commit": contract,
                    "correction_commit": correction,
                    "files": [frozen],
                    "ancillary_files": [
                        "docs/requirements/WMS-687.md",
                        regression,
                    ],
                    "review": {
                        "model": "gpt-6.1-sol",
                        "effort": "high",
                        "verdict": "PASS",
                        "report": report,
                    },
                }
            ) + "\n",
        )
        self.commit("WMS-687 correction ledger")

        self.assertTrue(checker.contract_change_errors(self.root, rollout))


if __name__ == "__main__":
    unittest.main()
