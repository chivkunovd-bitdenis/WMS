"""Offline immutable-source/receipt probe. Does not execute tests or updater."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = '756b45a4d46b9e9a33657549e2c2addb6bae89c1'
TEST = 'tools/print-agent/test_macos_direct_updater_contract.py'
REQ = 'docs/requirements/WMS-607.md'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)

def digest(data):
    return hashlib.sha256(data).hexdigest()

paths = git('ls-tree', '-r', '--name-only', BASE, 'tools/print-agent').decode().splitlines()
closure = []
for path in paths:
    before = git('show', BASE + ':' + path)
    now = git('show', 'HEAD:' + path)
    assert now == before, path
    local = REPO / path
    assert not local.exists() or local.read_bytes() == before, path
    closure.append({'path': path, 'git_blob': git('rev-parse', BASE + ':' + path).decode().strip(),
                    'sha256': digest(before), 'bytes': len(before)})
old = git('show', BASE + ':' + REQ).decode()
now = (REPO / REQ).read_text()
oldrows = {line.split('|')[1].strip(): line for line in old.splitlines() if line.startswith('| U-C')}
lines = now.splitlines()
for index, line in enumerate(lines):
    if not line.startswith('| U-C'):
        continue
    key = line.split('|')[1].strip()
    parts, original = line.split('|'), oldrows[key].split('|')
    assert parts[:5] == original[:5] and parts[6:] == original[6:], key
    if key in ('U-C9', 'U-C10'):
        assert line == oldrows[key], key
    else:
        assert original[5].strip() == '' and TEST in parts[5], key
    parts[5] = original[5]
    lines[index] = '|'.join(parts)
assert '\n'.join(lines) + '\n' == old, 'Non-Test-cell requirement change'
module = ast.parse((REPO / TEST).read_text())
cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'UpdaterContract')
methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
xml = ET.parse(HERE / 'precode.xml').getroot()
actual = [n.attrib['classname'] + '::' + n.attrib['name'] for n in xml.findall('testcase')]
expected = ['test_macos_direct_updater_contract.UpdaterContract::' + n for n in methods]
assert set(actual) == set(expected) and len(actual) == len(set(actual)) == 10
assert xml.attrib['failures'] == '8' and xml.attrib['errors'] == '0' and xml.attrib['skipped'] == '0'
for case in xml.findall('testcase'):
    failed = case.find('failure')
    assert (failed is not None) == case.attrib['name'].startswith('test_uc')
    if failed is not None:
        assert 'NOT IMPLEMENTED at BASE' in failed.text
    raw = json.loads((HERE / 'precode' / (case.attrib['name'] + '.json')).read_text())
    assert raw['test_sha256'] == digest((REPO / TEST).read_bytes())
    assert raw['entry_present'] is False and raw['executions'] == []
mutations = json.loads((HERE / 'mutation-result.json').read_text())
assert len(mutations) == 2 and all(x['meaningful_assertion_FAIL'] and x['tracked_source_unchanged'] for x in mutations)
for name in ('metadata', 'journal'):
    mx = ET.parse(HERE / ('mutation-' + name + '.xml')).getroot()
    assert (mx.attrib['tests'], mx.attrib['failures'], mx.attrib['errors'], mx.attrib['skipped']) == ('1', '1', '0', '0')
    raws = list((HERE / ('mutant-' + name)).glob('*.json'))
    assert len(raws) == 1
    assert json.loads(raws[0].read_text())['test_sha256'] == digest((REPO / TEST).read_bytes())
result = {'task': 'WMS-607', 'base': BASE, 'updater_entry': 'tools/print-agent/update_macos_direct.sh',
          'updater_entry_absent': not (REPO / 'tools/print-agent/update_macos_direct.sh').exists(),
          'test_sha256': digest((REPO / TEST).read_bytes()), 'xml_ids': expected,
          'precode': {'total': 10, 'PASS': 2, 'FAIL_missing_entry': 8, 'SKIP': 0, 'ERROR': 0,
                      'updater_behavior_executed': False},
          'requirements': {'base_sha256': digest(old.encode()), 'current_sha256': digest(now.encode()),
                           'only_eight_Test_cells_changed': True, 'R_U1_to_8_and_U_C1_to_10_preserved': True,
                           'manual_U_C9_10_unchanged': True},
          'existing_print_agent_files_unchanged': closure,
          'copy_mutations': mutations, 'no_product_or_installer_edits': True}
print(json.dumps(result, ensure_ascii=False, indent=2))
