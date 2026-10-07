"""Read-only provenance and exact-suite checks; never writes product or contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = 'a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72'
PRODUCT = '32c3212406eaf57b904c207bfb45d7acfd25a0b0'
def sha(data):
    return hashlib.sha256(data).hexdigest()
def git(ref, path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)

paths = [
    'tools/print-agent/test_macos_direct_updater_contract.py',
    'docs/evidence/WMS-607/updater-test-contract-20261007/run-contract.py',
    'docs/evidence/WMS-607/updater-test-contract-20261007/contract.json',
    'tools/print-agent/test_macos_artmaks_contract.py',
    'tools/print-agent/test_macos_default_printer.py',
    'tools/print-agent/test_macos_native.py',
    'tools/print-agent/test_macos_artmaks_http_contract.py',
    'tools/print-agent/wms_cups_observe.c',
    'tools/print-agent/history.html',
    'docs/requirements/WMS-607.md',
]
unchanged = []
for path in paths:
    before = git(BASE,path)
    after = (ROOT/path).read_bytes()
    assert before == after, path
    unchanged.append({'path':path,'sha256':sha(after),'bytes':len(after),'byte_unchanged_from_base':True})
products = []
for path in ('tools/print-agent/update_macos_direct.sh','tools/print-agent/build_console.py','tools/print-agent/wms_print_direct_macos.swift'):
    data = (ROOT/path).read_bytes()
    assert data == git(PRODUCT,path), path
    products.append({'path':path,'sha256':sha(data),'bytes':len(data)})
before = git(BASE,'tools/print-agent/wms_print_direct_macos.swift').decode()
after = (ROOT/'tools/print-agent/wms_print_direct_macos.swift').read_text()
normalized = after.replace('init(directory:URL,autoWork:Bool=true,resumeSaved:Bool=true,','init(directory:URL,autoWork:Bool=true,').replace('if autoWork && resumeSaved { for job in jobs.values','if autoWork { for job in jobs.values')
assert normalized.split('private struct HTTPRequest {')[0] == before.split('private struct HTTPRequest {')[0]
assert after.split('private struct HTTPRequest {')[1].split('private func runServer(')[0] == before.split('private struct HTTPRequest {')[1].split('private func runServer(')[0]
reports = {}
for name,count,failures in [('precode',10,8),('final',10,0),('existing',19,0)]:
    report = ET.parse(OUT/(name+'.xml')).getroot()
    assert (report.attrib['tests'],report.attrib['failures'],report.attrib['errors'],report.attrib['skipped']) == (str(count),str(failures),'0','0'), report.attrib
    reports[name] = report.attrib
precode_raw = sorted((OUT/'precode').glob('*.json'))
assert len(precode_raw) == 10
for path in precode_raw:
    data = json.loads(path.read_text())
    assert data['entry_present'] is False and data['entry_sha256'] is None, path
    assert data['source_sha256'] == sha(before.encode()), path
    assert data['test_sha256'] == unchanged[0]['sha256'], path
contract = json.loads((ROOT/paths[2]).read_text())
report = ET.parse(OUT/'final.xml').getroot()
actual_ids = [c.attrib['classname']+'::'+c.attrib['name'] for c in report.findall('testcase')]
assert sorted(actual_ids) == sorted(contract['suite']['xml_ids'])
raw = sorted((OUT/'final').glob('*.json'))
assert len(raw) == 10
for path in raw:
    data = json.loads(path.read_text())
    assert data['entry_sha256'] == products[0]['sha256'], path
    assert data['source_sha256'] == products[2]['sha256'], path
    assert data['test_sha256'] == unchanged[0]['sha256'], path
native = json.loads((OUT/'native-start.json').read_text())
assert native['pass'] and native['provenance']['source_sha256'] == products[2]['sha256']
repeat = json.loads((OUT/'default-repeat.json').read_text())
assert repeat['pass'] and repeat['entry_sha256'] == products[0]['sha256']
result = {'base':BASE,'product_source_commit':PRODUCT,'unchanged':unchanged,'products':products,'native_core_preserved_except_explicit_resumeSaved_option':True,'HTTP_and_native_selftest_bytes_unchanged':True,'native_source_before_sha256':sha(before.encode()),'native_source_after_sha256':sha(after.encode()),'reports':reports,'exact_final_XML_ids_and_all_10_raw_source_hashes':True,'separate_native_start_and_default_repeat':True,'independent_review':False,'analytical_acceptance':False}
(OUT/'preservation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
