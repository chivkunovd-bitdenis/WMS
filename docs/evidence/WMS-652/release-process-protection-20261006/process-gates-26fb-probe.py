"""Bounded independent audit of fixed Git bytes; collection only, no printer calls."""
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import io
import re

REPO = Path('/Users/deniscivkunov/Projects/WMS')
SHA = '26fb8462b9e319cbc38b9ce2f7d8a6815416b4a2'
PYTEST = REPO / 'backend/.venv/bin/python'
with tempfile.TemporaryDirectory(prefix='wms-astra-a-26fb-') as directory:
    root = Path(directory)
    raw = subprocess.check_output(['git', '-C', str(REPO), 'archive', SHA,
        'scripts/ci', 'tools/print-agent', 'guards/PROCESS_CONTRACTS.json', '.github/workflows/ci.yml'])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(root, filter='data')
    print('FROZEN_SHA', SHA, flush=True)
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
        'scripts/ci/tests', '-p', 'test_process*.py', '-v'], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, flush=True)
    assert result.returncode == 0
    policy = json.loads((root/'guards/PROCESS_CONTRACTS.json').read_text())
    cases = {}
    selectors = {
        'native-linux': 'not test_windows_cmd_synthetic_queue_receipt',
        'native-windows': 'not test_safe_synthetic_queue_runs_real_child_process_once and not test_actual_process_exit_after_spool_acceptance_recovers_without_second_submit',
    }
    for suite, selector in selectors.items():
        result = subprocess.run([str(PYTEST), '-m', 'pytest', '--collect-only', '-q',
            'tools/print-agent/test_wms_print_direct.py', 'tools/print-agent/test_wms_print_runtime.py',
            '-k', selector], cwd=root, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        nodes = [line for line in result.stdout.splitlines() if '.py::' in line]
        cases[suite] = {file.removesuffix('.py').replace('/', '.')+'.'+cls+'::'+test
            for file, cls, test in (node.split('::') for node in nodes)}
        assert cases[suite] == set(policy['suites'][suite]['cases'])
        assert policy['suites'][suite]['exact'] is True
        print('EXACT_COLLECTED', suite, len(cases[suite]), flush=True)
    assert len(cases['native-linux'] | cases['native-windows']) == 31
    print('UNION', 31, 'These are local collection results, not Windows execution.', flush=True)
    workflow = (root/'.github/workflows/ci.yml').read_text()
    for prefix in ['backend-executed-contracts', 'frontend-executed-contracts',
                   'printer-windows-contracts', 'release-print']:
        names = re.findall(r'name: ('+prefix+r'-[^\n]+)', workflow)
        expected = prefix+'-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}'
        assert names == [expected, expected], names
        print('PRODUCER_AND_CONSUMER', expected, flush=True)
    print('PASS: fixed platform selection, exact artifact attempt names, 20 gate contracts', flush=True)
