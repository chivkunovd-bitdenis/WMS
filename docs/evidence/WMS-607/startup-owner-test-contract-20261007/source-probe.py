"""Offline exact Git/source/receipt checks. No startup/tests/CI execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
BASE='a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6'
SOURCE='tools/print-agent/update_macos_direct.sh'
TEST='tools/print-agent/test_macos_direct_updater_start_owner_contract.py'
RECEIPT='71640d0c1160049f085bc6b524581ff25a804b1c'
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
def sha(d):return hashlib.sha256(d).hexdigest()
source=git('show',BASE+':'+SOURCE)
assert git('show','HEAD:'+SOURCE)==source
assert not (REPO/SOURCE).is_file() or (REPO/SOURCE).read_bytes()==source
old=git('ls-tree','-r','--name-only',BASE,'tools/print-agent','docs/evidence/WMS-607/updater-test-contract-20261007','docs/evidence/WMS-607/updater-stop-test-contract-20261007').decode().splitlines()
protected=[]
for path in old:
 data=git('show',BASE+':'+path);assert git('show','HEAD:'+path)==data,path
 local=REPO/path;assert not local.is_file() or local.read_bytes()==data,path
 protected.append({'path':path,'git_blob':git('rev-parse',BASE+':'+path).decode().strip(),'sha256':sha(data)})
assert git('show','HEAD:docs/requirements/WMS-607.md')==git('show',BASE+':docs/requirements/WMS-607.md')
oldten=git('show','a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72:tools/print-agent/test_macos_direct_updater_contract.py')
assert oldten==git('show',BASE+':tools/print-agent/test_macos_direct_updater_contract.py') and b'timeout=15)' in oldten
xml=ET.parse(HERE/'precode.xml').getroot()
assert (xml.attrib['tests'],xml.attrib['failures'],xml.attrib['errors'],xml.attrib['skipped'])==('3','1','0','0')
cases=[]
for case in xml.findall('testcase'):
 name=case.attrib['name'];raw=json.loads((HERE/'precode'/(name+'.json')).read_text())
 assert raw['source_sha256']==sha(source) and raw['test_sha256']==sha((REPO/TEST).read_bytes())
 assert raw['app_unchanged'] and raw['state_unchanged'] and raw['intent_unchanged'] and raw['fixture_launcher_released']
 assert not any(e.startswith('signal|') for e in raw['events'])
 failed=case.find('failure') is not None
 assert failed==name.startswith('test_confirmed_foreign')
 summary={'id':case.attrib['classname']+'::'+name,'assertion':'FAIL' if failed else 'PASS','startup_exit':raw['native_exit'],
          'event_counts':{key:raw['events'].count(key) for key in ('lsof','ps|foreign|42424242','ps|owned|42424242','startup-sleep','curl|health200','readiness')}}
 if failed:
  assert raw['native_exit']!=0
  first=raw['events'].index('ps|foreign|42424242')
  tail=raw['events'][first+1:]
  assert 'startup-sleep' in tail and 'lsof' in tail and 'curl|health200' not in raw['events']
 else:assert raw['native_exit']==0 and 'curl|health200' in raw['events'] and 'readiness' in raw['events']
 cases.append(summary)
mutation=json.loads((HERE/'mutation-result.json').read_text())
assert mutation['copies_removed'] and mutation['tracked_source_unchanged']
for c in mutation['controls']:
 assert c['source_sha256']==sha(source) and c['meaningful_assertion_FAIL'] and c['ERROR']==c['SKIP']==0
 raw=list((HERE/('mutation-'+c['name'])).glob('*.json'));assert len(raw)==1
 assert json.loads(raw[0].read_text())['test_sha256']==sha((REPO/TEST).read_bytes())
# Read only manifest + exact XML members, no download/replay of package.
prefix='docs/evidence/WMS-607/mac-package-37579919987/'
manifest_bytes=git('show',RECEIPT+':'+prefix+'raw-manifest.json');manifest=json.loads(manifest_bytes)
assert manifest['source']==BASE and manifest['run_id']==37579919987 and manifest['attempt']==1
historical=[]
for artifact in manifest['artifacts']:
 for member in artifact['members']:
  if member['stored_path'].endswith('.xml'):
   data=git('show',RECEIPT+':'+prefix+member['stored_path'])
   assert sha(data)==member['original_sha256']==member['stored_sha256'] and len(data)==member['original_bytes']
   root=ET.fromstring(data)
   historical.append({'architecture':artifact['architecture'],'path':prefix+member['stored_path'],'sha256':sha(data),'suite':root.attrib})
intel=next(x for x in historical if x['architecture']=='x86_64')
assert (intel['suite']['tests'],intel['suite']['failures'],intel['suite']['errors'],intel['suite']['skipped'])==('10','0','1','0')
result={'base':BASE,'updater':{'path':SOURCE,'git_blob':git('rev-parse',BASE+':'+SOURCE).decode().strip(),'sha256':sha(source)},
        'test':{'path':TEST,'sha256':sha((REPO/TEST).read_bytes())},'precode':{'total':3,'PASS':2,'target_behavior_FAIL':1,'ERROR':0,'SKIP':0,'runner_exit':1,'cases':cases},
        'old_print_agent_and_contract_paths_unchanged':protected,'old10_deadline_15_seconds_unchanged':True,'requirements_unchanged':True,
        'historical_receipts':{'commit':RECEIPT,'manifest_sha256':sha(manifest_bytes),'run_id':37579919987,'attempt':1,'xml_members':historical,
                              'historical_Intel_CPU_timing_cause_proven':False},'copy_controls':mutation,'no_product_implementation':True}
print(json.dumps(result,indent=2))
