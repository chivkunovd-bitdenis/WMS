import importlib.util
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

    def test_sol61_high_review_cannot_accept_corrected_contract(self):
        self.assertTrue(any("реестр коррекции" in error
                            for error in self.sol61_correction_errors("high")))

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

    def test_array_corrections_reject_sol_high_review(self):
        rollout, _, _, entries = self.disjoint_corrections()
        entries[1]["review"]["model"] = "gpt-6.1-sol"
        self.save_corrections(entries)
        errors = checker.contract_change_errors(self.root, rollout)
        self.assertTrue(any("заполнен не полностью" in error for error in errors), errors)

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


if __name__ == "__main__":
    unittest.main()
