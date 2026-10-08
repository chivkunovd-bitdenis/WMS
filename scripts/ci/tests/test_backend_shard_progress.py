"""Controller progress output is diagnostic and does not change shard receipts."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class BackendShardProgressContracts(unittest.TestCase):
    def test_progress_records_identity_start_phases_and_failure_detail_as_jsonl(self):
        module = importlib.import_module('scripts.ci.backend_shards')
        identity = {'sha': 'a' * 40, 'run_id': 100, 'run_attempt': 2}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.jsonl'
            progress = module.Progress(path, identity, 1)
            progress.pytest_runtest_logstart(
                'tests/test_example.py::test_case',
                ('tests/test_example.py', 12, 'test_case'))

            # Reopening the file here proves each hook flushed its record.
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['event'], 'logstart')
            self.assertEqual(records[0]['nodeid'], 'tests/test_example.py::test_case')
            self.assertEqual(records[0]['location'], ['tests/test_example.py', 12, 'test_case'])

            progress.pytest_runtest_logreport(SimpleNamespace(
                nodeid='tests/test_example.py::test_case', when='setup', outcome='passed',
                duration=0.125, failed=False, longrepr=None))
            progress.pytest_runtest_logreport(SimpleNamespace(
                nodeid='tests/test_example.py::test_case', when='call', outcome='failed',
                duration=0.25, failed=True, longrepr='assert 1 == 2'))

            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertTrue(all({key: row[key] for key in identity} == identity for row in records))
            self.assertTrue(all(row['shard_index'] == 1 for row in records))
            self.assertEqual([(row['phase'], row['outcome']) for row in records[1:]],
                             [('setup', 'passed'), ('call', 'failed')])
            self.assertEqual(records[1]['duration_seconds'], 0.125)
            self.assertEqual(records[2]['longrepr'], 'assert 1 == 2')

    def test_actual_xdist_run_writes_controller_progress_without_receipt_changes(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            case = temp / 'test_probe.py'
            case.write_text('def test_probe():\n    assert True\n')
            output = temp / 'shard'
            environment = {**os.environ, 'GITHUB_SHA': 'a' * 40,
                           'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '2',
                           'GITHUB_ACTIONS': 'false'}
            result = subprocess.run([
                sys.executable, str(root / 'scripts/ci/backend_shards.py'), 'run',
                '--index', '0', '--output', str(output), '--', '-n', '2', '-q', str(case)],
                cwd=temp, env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertEqual(receipt['exit_code'], 0)
            self.assertEqual(receipt['selected'], ['test_probe.py::test_probe'])
            rows = [json.loads(line) for line in (output / 'progress.jsonl').read_text().splitlines()]
            self.assertEqual([row['event'] for row in rows].count('logstart'), 1)
            reports = [row for row in rows if row['event'] == 'logreport']
            self.assertEqual({row['phase'] for row in reports}, {'setup', 'call', 'teardown'})
            self.assertTrue(all(row['nodeid'] == 'test_probe.py::test_probe' for row in rows))
            self.assertTrue(all(row['outcome'] == 'passed' for row in reports))


if __name__ == '__main__':
    unittest.main()
