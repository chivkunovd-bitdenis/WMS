"""WMS-652 additive pre-implementation contract: producer gate and setup errors."""
import importlib
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.ci.tests.test_backend_shards import IDENTITY, IDS, ROOT, fixture


class BackendFailClosedContracts(unittest.TestCase):
    def test_actual_aggregator_shell_refuses_any_missing_skipped_or_failed_producer(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        job = raw.split('\n  backend:\n', 1)[1].split('\n  print-regressions:', 1)[0]
        step = job.split('      - name: Require every backend producer to succeed\n', 1)[1]
        body = step.split('        run: |\n', 1)[1].split('      - uses:', 1)[0]
        command = '\n'.join(line[10:] for line in body.splitlines())
        for left in ['success', 'failure', 'skipped', 'cancelled', '']:
            for right in ['success', 'failure', 'skipped', 'cancelled', '']:
                with self.subTest(checks=left, shards=right):
                    result = subprocess.run(['bash', '-e', '-c', command], check=False,
                        capture_output=True, env={'PATH': '/usr/bin:/bin',
                            'CHECKS_RESULT': left, 'SHARDS_RESULT': right})
                    self.assertEqual(result.returncode == 0, left == right == 'success')

    def test_collection_setup_error_outside_case_is_preserved_and_cannot_be_green(self):
        module = importlib.import_module('scripts.ci.backend_shards')
        with tempfile.TemporaryDirectory() as folder:
            paths = fixture(folder)
            source = paths[0]/'junit.xml'
            tree = ET.parse(source)
            ET.SubElement(tree.getroot().find('testsuite'), 'error', message='collection').text = 'original setup detail'
            tree.write(source)
            output = Path(folder)/'merged.xml'
            result = module.merge(paths, output, IDENTITY)
            self.assertFalse(result['success'])
            self.assertEqual(result['errors'], 1)
            self.assertEqual(next(ET.parse(output).iter('error')).text, 'original setup detail')

    def test_worker_collection_drift_fails_before_any_body_runs(self):
        module = importlib.import_module('scripts.ci.backend_shards')
        item = SimpleNamespace(nodeid=IDS[0], user_properties=[])
        with patch.dict(os.environ, {'WMS_BACKEND_SHARD_INDEX': '0',
                'WMS_BACKEND_COLLECTION_DIGEST': module.digest(IDS)}), self.assertRaises(ValueError):
            module.pytest_collection_modifyitems(SimpleNamespace(), [item])
        self.assertEqual(item.user_properties, [])


if __name__ == '__main__':
    unittest.main()
