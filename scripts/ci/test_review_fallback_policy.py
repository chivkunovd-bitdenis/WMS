"""WMS-735: owner's review model rule (10.10.2026) — Opus 5.5 high in Claude, Astra high in Codex."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReviewModelPolicyTests(unittest.TestCase):
    def test_agent_rule_files_match(self) -> None:
        self.assertEqual((ROOT / "AGENTS.md").read_bytes(), (ROOT / "CLAUDE.md").read_bytes())

    def test_review_model_depends_on_environment_and_gates_stay(self) -> None:
        rules = (ROOT / "AGENTS.md").read_text()
        start = rules.index("**Ревью.**")
        review = rules[start:rules.index("Передай ревьюеру требования", start)]
        for required in (
            "в Claude ревью всегда выполняет Claude Opus 5.5 с effort high",
            "в Codex ревью всегда выполняет Astra с явно заданным effort `high`",
            "включая CI, облачный CLI и вложенных агентов",
            "ожидание не даёт права пропустить ревью",
            "Собственная проверка разработчика",
            "не считаются пройденным этапом",
            "Тесты, приёмка и полный CI остаются обязательными",
            "предел Astra — не выше `high`",
        ):
            with self.subTest(required=required):
                self.assertIn(required, review)
        self.assertNotIn("Sol 6.1", review)


if __name__ == "__main__":
    unittest.main()
