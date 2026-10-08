"""Renamed runtime inputs must keep the full CI wave enabled."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci.ci_scope import changed_paths, full_wave


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
