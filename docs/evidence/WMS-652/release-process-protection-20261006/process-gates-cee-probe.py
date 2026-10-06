"""Read-only reproduction against fixed Git objects, no product/test modification."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
import types
import xml.etree.ElementTree as ET

SHA = 'cee68a42dd43aee1a7f6cf86277e6fb697133171'
SOURCE = Path('/Users/deniscivkunov/Projects/WMS/.worktrees/wms652-process-gates')
def source(path):
    return subprocess.check_output(['git', '-C', str(SOURCE), 'show', f'{SHA}:{path}']).decode()
policy = json.loads(source('guards/PROCESS_CONTRACTS.json'))
module = types.ModuleType('audited_process_contracts')
exec(compile(source('scripts/ci/process_contracts.py'), 'frozen-process_contracts.py', 'exec'), module.__dict__)
windows = policy['suites']['native-windows']
blocked = {'test_safe_synthetic_queue_runs_real_child_process_once',
           'test_actual_process_exit_after_spool_acceptance_recovers_without_second_submit'}
for node in ast.walk(ast.parse(source('tools/print-agent/test_wms_print_runtime.py'))):
    if isinstance(node, ast.FunctionDef) and node.name in blocked:
        print('WINDOWS_GUARD', node.name, ast.unparse(node.body[0]))
root = ET.Element('testsuite')
for case in windows['cases']:
    classname, name = case.rsplit('::', 1)
    child = ET.SubElement(root, 'testcase', classname=classname, name=name)
    if name in blocked:
        ET.SubElement(child, 'skipped')
with tempfile.TemporaryDirectory(prefix='wms-a-review-') as temp:
    directory = Path(temp)
    (directory / windows['report']).write_bytes(ET.tostring(root))
    try:
        module.verify_reports({**policy, 'suites': {'native-windows': windows}}, directory)
    except ValueError as error:
        print('REPRODUCED_REQUIRED_WINDOWS_REPORT_REFUSAL', error)
    else:
        raise AssertionError('Expected the required Windows skip report to be refused')
workflow = source('.github/workflows/ci.yml')
for line in workflow.splitlines():
    if 'name:' in line and any(x in line for x in ['executed-contracts-', 'printer-windows-contracts-', 'release-print-', 'process-proof-${']):
        print('ARTIFACT_NAME_WIRING', line.strip())
