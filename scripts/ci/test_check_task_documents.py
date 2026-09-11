import importlib.util
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


if __name__ == "__main__":
    unittest.main()
