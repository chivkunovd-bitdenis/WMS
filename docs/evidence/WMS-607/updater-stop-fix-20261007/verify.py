"""Read-only P1 provenance; all frozen contracts and prior sources stay exact."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = '6232cf29765f1b25466e96919ee7840bf5874c62'
SOURCE = 'bdd5a8eee8606d667a90a3b61da299b4097dc877'
SHELL = 'tools/print-agent/update_macos_direct.sh'
sha = lambda data: hashlib.sha256(data).hexdigest()
def git_bytes(ref, path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)
def tracked(ref, *paths):
    return subprocess.check_output(['git','ls-tree','-r','--name-only',ref,'--',*paths],cwd=ROOT,text=True).splitlines()

groups = {}
for name,ref,paths in [
    ('new_frozen_contract','040e94c956b8cc99d69d04e8cc90499a01e61a95',('tools/print-agent/test_macos_direct_updater_stop_contract.py','docs/evidence/WMS-607/updater-stop-test-contract-20261007')),
    ('new_handoff','6b85c90e4719dc652e595321f268ca96a62d982a',('docs/evidence/WMS-607/updater-stop-test-contract-20261007/result.md',)),
    ('old_frozen_contract','a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72',('tools/print-agent/test_macos_direct_updater_contract.py','docs/evidence/WMS-607/updater-test-contract-20261007')),
    ('prior_print_sources_and_tests',BASE,('tools/print-agent','docs/requirements/WMS-607.md')),
]:
    records = []
    for path in tracked(ref,*paths):
        if path == SHELL:
            continue
        old = git_bytes(ref,path)
        assert old == git_bytes('HEAD',path),path
        local = ROOT/path
        if local.is_file():
            assert local.read_bytes() == old,path
        records.append({'path':path,'sha256':sha(old)})
    groups[name] = records

before = sha(git_bytes(BASE,SHELL))
after = sha((ROOT/SHELL).read_bytes())
assert (ROOT/SHELL).read_bytes() == git_bytes(SOURCE,SHELL)
reports = {}
for name,count,failures in [('precode',4,2),('green',4,0),('updater',10,0),('existing',19,0)]:
    report = ET.parse(OUT/(name+'.xml')).getroot()
    assert tuple(report.get(k) for k in ('tests','failures','errors','skipped')) == (str(count),str(failures),'0','0'),report.attrib
    reports[name] = report.attrib
    if name in ('precode','green','updater'):
        contract_path = ('docs/evidence/WMS-607/updater-test-contract-20261007/contract.json' if name == 'updater' else 'docs/evidence/WMS-607/updater-stop-test-contract-20261007/contract.json')
        contract = json.loads(git_bytes('HEAD',contract_path))
        ids = [x.get('classname')+'::'+x.get('name') for x in report.findall('testcase')]
        assert sorted(ids) == sorted(contract['suite']['xml_ids'])
        records = list((OUT/name).glob('*.json'))
        assert len(records) == count
        for path in records:
            data = json.loads(path.read_text())
            assert data.get('source_sha256') == (before if name == 'precode' else sha((ROOT/'tools/print-agent/wms_print_direct_macos.swift').read_bytes()) if name == 'updater' else after),path
            if name == 'updater':
                assert data['entry_sha256'] == after,path
            else:
                assert data['test_sha256'] == sha((ROOT/'tools/print-agent/test_macos_direct_updater_stop_contract.py').read_bytes()),path
result = {'source_commit':SOURCE,'base':BASE,'review':'30ffc6bce9fffcdc1b4e0b95b9c8782bfb41896c','source_sha256_before':before,'source_sha256_after':after,'reports':reports,'byte_exact_preservation':groups,'new_packages_built':False,'prior_ARM_artifact_source':'32c3212406eaf57b904c207bfb45d7acfd25a0b0','prior_ARM_artifact_is_final':False,'independent_rereview':False,'analytical_acceptance':False}
(OUT/'preservation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'source_commit':SOURCE,'source_sha256':after,'reports':reports,'unchanged_counts':{name:len(records) for name,records in groups.items()}},indent=2))
