"""WMS-652 CLI preservation and discovered null-merge failure publication contract."""
import contextlib
import importlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ci.tests.test_trusted_process_artifact import ArtifactFixture
from scripts.ci.tests.test_trusted_process_check import REPO, H


class TrustedCliTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.ci.trusted_process_check')
        self.f = ArtifactFixture()

    def invoke(self, arguments, environment, event=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            path.write_text(json.dumps(event or {}))
            argv = ['trusted_process_check.py', '--repository', REPO, *arguments]
            if event is not None:
                argv.extend(['--event', str(path)])
            with patch.dict(os.environ, environment, clear=True), patch('sys.argv', argv), \
                    patch.object(self.m, 'api_get', self.f.get), \
                    patch.object(self.m, 'download_artifact', self.f.download), \
                    patch.object(self.m, 'publish') as published, \
                    contextlib.redirect_stdout(io.StringIO()):
                code = self.m.main()
                return code, published.call_args_list

    def test_read_only_cli_always_requires_artifact_and_never_publishes(self):
        self.f.artifacts = []
        code, published = self.invoke(['--pr', '7'], {})
        self.assertEqual(code, 2)
        self.assertEqual(published, [])
        self.f = ArtifactFixture()
        code, published = self.invoke(['--pr', '7'], {})
        self.assertEqual(code, 0)
        self.assertEqual(published, [])

    def test_cli_cannot_publish_from_pr_flag_or_outside_workflow(self):
        for args, env in [(['--pr', '7', '--publish'], {}),
                          (['--pr', '7', '--publish'], {'GITHUB_ACTIONS': 'true'})]:
            with self.subTest(args=args, env=env), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.invoke(args, env)

    def test_missing_proof_publishes_failure_only_on_exact_pr_head(self):
        self.f.artifacts = []
        code, published = self.invoke(['--publish'], {'GITHUB_ACTIONS': 'true',
            'GITHUB_EVENT_NAME': 'pull_request_target'}, {'pull_request': {'number': 7}})
        self.assertEqual(code, 2)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].args[:3], (REPO, H, 'failure'))
        self.assertIs(published[0].args[3]['evidence_complete'], False)

    def test_null_merge_still_publishes_failure_on_exact_pr_head(self):
        self.f.pr['merge_commit_sha'] = None
        code, published = self.invoke(['--publish'], {'GITHUB_ACTIONS': 'true',
            'GITHUB_EVENT_NAME': 'pull_request_target'}, {'pull_request': {'number': 7}})
        self.assertEqual(code, 2)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].args[:3], (REPO, H, 'failure'))


if __name__ == '__main__':
    unittest.main()
