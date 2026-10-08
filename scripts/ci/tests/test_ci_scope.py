"""Renamed runtime inputs must keep the full CI wave enabled."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci.ci_scope import changed_paths, full_wave


class FullWaveScopeTests(unittest.TestCase):
    def test_process_checker_source_change_is_not_docs_only(self):
        self.assertTrue(full_wave(['scripts/ci/trusted_process_check.py'], 'pull_request'))

    def test_prose_document_change_can_skip_heavy_wave(self):
        self.assertFalse(full_wave(['docs/requirements/WMS-704.md'], 'pull_request'))


class WorkflowScopeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            Path(__file__).resolve().parents[3] / '.github' / 'workflows' / 'ci.yml'
        ).read_text(encoding='utf-8')

    def test_workflow_files_route_through_process_checks(self):
        filter_block = self.workflow.split('process_checks:\n', 1)[1].split('\n\n', 1)[0]
        self.assertIn("- '.github/workflows/ci.yml'", filter_block)
        self.assertIn("- '.github/workflows/process-integrity.yml'", filter_block)
        self.assertIn("- 'scripts/ci/**'", filter_block)

    def test_heavy_jobs_run_for_manual_dispatch_or_scope_failure(self):
        for name in ('backend', 'e2e'):
            expected = (
                "if: always() && (github.event_name != 'pull_request' || "
                "needs.change-scope.result != 'success' || "
                f"needs.change-scope.outputs.{name} == 'true')"
            )
            self.assertIn(expected, self.workflow)


class ChangedPathRenameTests(unittest.TestCase):
    def test_runtime_to_docs_rename_keeps_old_path_in_full_wave_scope(self):
        with tempfile.TemporaryDirectory(prefix='wms-ci-scope-rename-') as folder:
            root = Path(folder)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'CI scope test')
            git('config', 'user.email', 'ci-scope@example.invalid')
            old = root / 'backend/app/services/runtime.py'
            old.parent.mkdir(parents=True)
            old.write_text('runtime input')
            git('add', '.')
            git('commit', '-qm', 'runtime baseline')
            base = git('rev-parse', 'HEAD')
            new = root / 'docs/removed-runtime.md'
            new.parent.mkdir(parents=True)
            old.rename(new)
            git('add', '-A')
            git('commit', '-qm', 'rename runtime to docs')
            head = git('rev-parse', 'HEAD')

            paths = changed_paths(root, base, head)
            self.assertEqual(set(paths), {'backend/app/services/runtime.py', 'docs/removed-runtime.md'})
            self.assertTrue(full_wave(paths, 'pull_request'))


if __name__ == '__main__':
    unittest.main()
