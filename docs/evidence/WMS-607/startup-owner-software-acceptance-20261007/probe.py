"""Read immutable Git source and saved receipts; execute no product or tests."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
BASE = '7cf184f80846eb500753998b27d8b04d04c0a536'
PRODUCT = '7bbcdd8a8aba9fd44dd4ee4ce2dbdee5af26b880'
FREEZE = '7b94a8dd0f1d6a772272930df3894d3ccd299686'
PREVIOUS = 'a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6'
P = 'docs/evidence/WMS-607/'
def git(*args):
    return subprocess.check_output(['git', *args])
def blob(path, ref=BASE):
    return git('show', ref + ':' + path)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def obj(path):
    return json.loads(blob(P + path))
source_path = 'tools/print-agent/update_macos_direct.sh'
source_hash = sha(blob(source_path))
assert blob(source_path) == blob(source_path, PRODUCT)
assert git('diff-tree','--no-commit-id','--name-only','-r',PRODUCT).decode().splitlines() == [source_path]
assert git('show','--format=','--numstat',PRODUCT).decode().strip() == '7\t3\t' + source_path
contract = obj('startup-owner-test-contract-20261007/contract.json')
manifest = obj('startup-owner-test-contract-20261007/manifest.json')
for m in manifest['members']:
    data = blob(m['path'])
    assert data == blob(m['path'], FREEZE)
    assert sha(data) == m['sha256'] and len(data) == m['bytes']
module = 'tools/print-agent/test_macos_direct_updater_start_owner_contract.py'
assert blob(module) == blob(module, FREEZE)
old_paths = git('ls-tree','-r','--name-only',PREVIOUS,'--','tools/print-agent').decode().splitlines()
for path in old_paths:
    if path != source_path:
        assert blob(path) == blob(path, PREVIOUS)
reports = {}
for name, count, failures in [('precode',3,1),('green',3,0),('rollback',4,0),('updater',10,0),('existing',19,0)]:
    path = P + 'startup-owner-fix-20261007/' + name + '.xml'
    root = ET.fromstring(blob(path));cases = list(root.iter('testcase'))
    ids = [c.get('classname') + '::' + c.get('name') for c in cases]
    assert len(ids) == len(set(ids)) == count
    assert sum(c.find('failure') is not None for c in cases) == failures
    assert not any(c.find('error') is not None or c.find('skipped') is not None for c in cases)
    if name in ['precode','green']:
        assert set(ids) == set(contract['suite']['xml_ids'])
    else:
        prior = {'rollback':'green','updater':'updater','existing':'existing'}[name]
        old = ET.fromstring(blob(P+'updater-stop-fix-20261007/'+prior+'.xml',PREVIOUS))
        assert set(ids) == {c.get('classname')+'::'+c.get('name') for c in old.iter('testcase')}
    reports[name] = {'tests':count,'pass':count-failures,'fail':failures,'error':0,'skip':0,'xml_ids':ids,'sha256':sha(blob(path))}
raw = []
for case in contract['suite']['xml_ids']:
    path = P+'startup-owner-fix-20261007/green/'+case.split('::')[1]+'.json'
    record = json.loads(blob(path))
    assert record['case'] == case and record['source_sha256'] == source_hash
    assert record['test_sha256'] == sha(blob(module))
    assert record['app_unchanged'] and record['state_unchanged'] and record['intent_unchanged']
    raw.append({'path':path,'sha256':sha(blob(path)),'source_sha256':record['source_sha256'],'native_exit':record['native_exit'],'mode':record['mode']})
proof = {'base':BASE,'product':PRODUCT,'frozen_contract':FREEZE,'source_sha256':source_hash,
         'source_git_blob':git('rev-parse',BASE+':'+source_path).decode().strip(),
         'source_delta':'one updater file 7 insertions / 3 deletions',
         'manifest_members_verified':len(manifest['members']),
         'previous_print_agent_paths_preserved_except_owned_shell':len(old_paths)-1,
         'reports':reports,'final_unique_software_cases':36,'new_raw_records':raw,
         'historic_package_receipt_commit':'71640d0c1160049f085bc6b524581ff25a804b1c',
         'historic_package_result_sha256':sha(blob(P+'mac-package-37579919987/result.md','71640d0c1160049f085bc6b524581ff25a804b1c')),
         'old_15_second_test_deadline_byte_preserved':True,'runtime_tests_or_build_executed_here':False}
Path(__file__).with_name('source-probe.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Saved source/receipt readback: precode1RED2PASS; final3+4+10+19=36PASS0error/skip; old files unchanged.')
