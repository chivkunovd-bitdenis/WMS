"""Offline source/receipt accounting only; no tests, process or updater execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BASE='6232cf29765f1b25466e96919ee7840bf5874c62'
FROZEN='a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72'
SOURCE='tools/print-agent/update_macos_direct.sh'
TEST='tools/print-agent/test_macos_direct_updater_stop_contract.py'
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
def sha(data):return hashlib.sha256(data).hexdigest()
source=git('show',BASE+':'+SOURCE)
assert git('show','HEAD:'+SOURCE)==source
assert not (REPO/SOURCE).is_file() or (REPO/SOURCE).read_bytes()==source
closure=git('ls-tree','-r','--name-only',FROZEN,'docs/evidence/WMS-607/updater-test-contract-20261007','tools/print-agent/test_macos_direct_updater_contract.py').decode().splitlines()
assert len(closure)==28
for path in closure:assert git('show','HEAD:'+path)==git('show',FROZEN+':'+path),path
assert git('show','HEAD:docs/requirements/WMS-607.md')==git('show',BASE+':docs/requirements/WMS-607.md')
xml=ET.parse(HERE/'precode.xml').getroot()
assert (xml.attrib['tests'],xml.attrib['failures'],xml.attrib['errors'],xml.attrib['skipped'])==('4','2','0','0')
ids=[]; outcomes=[]
for case in xml.findall('testcase'):
    name=case.attrib['name']; identifier=case.attrib['classname']+'::'+name; ids.append(identifier)
    raw=json.loads((HERE/'precode'/(name+'.json')).read_text())
    assert raw['source_sha256']==sha(source) and raw['test_sha256']==sha((REPO/TEST).read_bytes())
    assert raw['case']==identifier
    failed=case.find('failure') is not None
    assert failed==name.startswith('test_owned_TERM_')
    if failed:
        assert raw['process_alive'] and raw['native_exit']!=0
        assert raw['after']['app']!=raw['before']['app'] and not raw['intent_unchanged'] and raw['transaction']==0
        assert raw['signals'].count('-TERM 42424242')==1
    assert raw['after']['state']==raw['before']['state']
    outcomes.append({'id':identifier,'assertion':'FAIL' if failed else 'PASS','native_rollback_exit':raw['native_exit'],
                     'process_alive':raw['process_alive'],'transaction':raw['transaction'],'intent_unchanged':raw['intent_unchanged']})
assert len(set(ids))==4
mutation=json.loads((HERE/'mutation-result.json').read_text())
assert mutation['tracked_source_unchanged'] and mutation['temporary_copies_removed']
for control in mutation['controls']:
    assert control['assertion_FAIL'] and control['ERROR']==control['SKIP']==0
    assert control['source_sha256']==sha(source)
    mx=ET.parse(HERE/('mutation-'+control['name']+'.xml')).getroot()
    assert (mx.attrib['tests'],mx.attrib['failures'],mx.attrib['errors'],mx.attrib['skipped'])==('1','1','0','0')
result={'base':BASE,'old_frozen_contract':FROZEN,'updater':{'path':SOURCE,'git_blob':git('rev-parse',BASE+':'+SOURCE).decode().strip(),
        'mode':git('ls-tree',BASE,SOURCE).decode().split()[0],'sha256':sha(source)},
        'test':{'path':TEST,'sha256':sha((REPO/TEST).read_bytes())},'xml_ids':ids,
        'precode':{'total':4,'PASS':2,'target_behavior_FAIL':2,'ERROR':0,'SKIP':0,'native_runner_exit':1,'cases':outcomes},
        'frozen_28_paths_unchanged':closure,'requirements_unchanged':True,'copy_controls':mutation,
        'product_source_unchanged':True}
print(json.dumps(result,indent=2))
