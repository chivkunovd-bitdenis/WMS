import importlib.util
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "resolve_ci_base.py"
spec = importlib.util.spec_from_file_location("baseline", SCRIPT)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        # Use existing repository commit identities; never change its HEAD or index.
        self.head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        self.before = subprocess.check_output(
            ["git", "rev-parse", "HEAD^"], text=True
        ).strip()

    def test_pull_request_uses_event_base(self):
        self.assertEqual(
            baseline.resolve_base(
                "pull_request",
                {"pull_request": {"base": {"sha": self.before}}},
                self.head,
            ),
            self.before,
        )

    def test_push_uses_before_even_if_origin_already_points_to_head(self):
        self.assertEqual(
            baseline.resolve_base("push", {"before": self.before}, self.head),
            self.before,
        )

    def test_first_push_fails_with_manual_recovery(self):
        with self.assertRaisesRegex(ValueError, "workflow_dispatch.*base_sha"):
            baseline.resolve_base("push", {"before": "0" * 40}, self.head)

    def test_manual_requires_explicit_earlier_sha(self):
        self.assertEqual(
            baseline.resolve_base(
                "workflow_dispatch", {"inputs": {"base_sha": self.before}}, self.head
            ),
            self.before,
        )
        for value in ("", self.head, "origin/etalon", "a" * 39):
            with self.subTest(value=value), self.assertRaises(ValueError):
                baseline.resolve_base(
                    "workflow_dispatch", {"inputs": {"base_sha": value}}, self.head
                )

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            baseline.resolve_base("push", {"before": self.head}, self.before)


if __name__ == "__main__":
    unittest.main()
