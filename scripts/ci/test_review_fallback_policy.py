"""WMS-676: retain the owner's explicit independent-review fallback rule."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReviewFallbackPolicyTests(unittest.TestCase):
    def test_agent_rule_files_match(self) -> None:
        self.assertEqual((ROOT / "AGENTS.md").read_bytes(), (ROOT / "CLAUDE.md").read_bytes())

    def test_sol_fallback_is_independent_astra_high_without_bypassing_gates(self) -> None:
        rules = (ROOT / "AGENTS.md").read_text()
        start = rules.index("Если Sol 6.1 недоступна, ревью выполняет отдельная независимая сессия Astra")
        fallback = rules[start:rules.index("Передай ревьюеру требования", start)]
        for required in (
            "отдельная независимая сессия Astra",
            "effort `high`",
            "включая CI, облачный CLI",
            "и вложенных агентов",
            "Ожидание Sol 6.1 не блокирует выпуск",
            "отдельного согласования замены не требуется",
            "Собственная проверка разработчика",
            "не считаются пройденным этапом",
            "Тесты, приёмка и полный CI остаются обязательными",
            "предел Astra — не выше `high`",
        ):
            with self.subTest(required=required):
                self.assertIn(required, fallback)


if __name__ == "__main__":
    unittest.main()
