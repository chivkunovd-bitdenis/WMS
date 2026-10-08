import unittest
from pathlib import Path

from scripts.ci.ci_scope import full_wave


class CIScopeTests(unittest.TestCase):
    def test_docs_prose_skips_full_wave(self):
        self.assertFalse(full_wave([
            "AGENTS.md", "CLAUDE.md", "docs/requirements/WMS-704.md",
            "docs/evidence/WMS-704/run.md",
        ], "pull_request"))

    def test_runtime_fixtures_and_ci_sources_run_full_wave(self):
        for path in (
            "docs/mockups/WMS-686/model.test.ts",
            "docs/evidence/WMS-704/fixture.json",
            "docs/requirements/WMS-704.pdf",
            "frontend/src/screens/v2/packing.ts",
            "scripts/ci/run_release_print.sh",
        ):
            with self.subTest(path=path):
                self.assertTrue(full_wave([path], "pull_request"))

    def test_manual_dispatch_always_runs_full_wave(self):
        self.assertTrue(full_wave(["docs/requirements/WMS-704.md"], "workflow_dispatch"))

    def test_fbs_workflows_filter_prose_and_source_test_only_changes(self):
        root = Path(__file__).resolve().parents[3]
        for name in ("fbs-picking.yml", "fbs-main-screen.yml"):
            workflow = (root / ".github/workflows" / name).read_text()
            with self.subTest(workflow=name):
                self.assertIn("paths:", workflow)
                self.assertIn("!frontend/src/**/*.test.ts", workflow)
                self.assertIn("workflow_dispatch:", workflow)
                self.assertIn("outside the push list", workflow)


if __name__ == "__main__":
    unittest.main()
