"""Independent bounded negative probes against frozen Git bytes; no live API."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

SHA = 'b096cd12916e63e8ee7507f508f00dd8526c15fa'
REPO = '/Users/deniscivkunov/Projects/WMS'
with tempfile.TemporaryDirectory(prefix='wms-audit-bootstrap-') as folder:
    root = Path(folder)
    raw = subprocess.check_output(['git', '-C', REPO, 'archive', SHA, 'scripts/ci'])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(root, filter='data')
    sys.path.insert(0, str(root))
    from scripts.ci import trusted_process_check as m
    from scripts.ci.tests.test_trusted_process_bootstrap import BootstrapFixture, PIN, S
    from scripts.ci.tests.test_trusted_process_check import REPO as API_REPO

    def rejects(label, operation):
        try:
            operation()
        except ValueError:
            print(label, 'REJECTED')
        else:
            raise AssertionError(label + ' was incorrectly accepted')

    checker = root/'standalone.py'
    checker.touch()
    config = checker.with_name('process_bootstrap.json')
    target = root/'other.json'
    target.write_text(json.dumps(PIN))
    with patch.object(m, '__file__', str(checker)):
        config.symlink_to(target)
        rejects('SYMLINK_PIN', m.load_approved_bootstrap)
        config.unlink()
        config.write_bytes(b' ' * (m.MAX_METADATA + 1))
        rejects('OVERSIZED_PIN', m.load_approved_bootstrap)

    fixture = BootstrapFixture()
    fixture.source_tree[-1]['mode'] = '120000'
    rejects('SOURCE_POLICY_SYMLINK', lambda: m.verify_pr_evidence(
        fixture.get, fixture.download, API_REPO, 7, approved_bootstrap=PIN))

    fixture = BootstrapFixture()
    original = fixture.get
    def truncated(path):
        result = original(path)
        if path.split('?')[0].endswith('/git/trees/'+S):
            result['truncated'] = True
        return result
    rejects('SOURCE_TREE_TRUNCATED', lambda: m.verify_pr_evidence(
        truncated, fixture.download, API_REPO, 7, approved_bootstrap=PIN))
    print('PASS', SHA, 'four additional fail-closed cases')
