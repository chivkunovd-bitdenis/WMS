"""Immutable final scope/policy/producers audit. Never edits integration."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType
import xml.etree.ElementTree as ET
import yaml

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
H='acf62b24a39565957f779c63b46cf573f8208d63'
P='b2a03ec118f9b4a184edfc4c2973ff92e044fd6c'
BASE='4c532f0cccfb8f99b34d68d9630a3763038fbc5f'
ACCEPTED='10c018092ab6f76928a54115eb824a64adc637be'
OLD='0151a555ac429957d0eee591317cc4326e909dfd'
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def blob(ref,path):return git('show',f'{ref}:{path}')
def data(ref,path):return json.loads(blob(ref,path))
def module(path):
 m=ModuleType('immutable_'+Path(path).stem);m.__file__=str(ROOT/path)
 exec(compile(blob(H,path),m.__file__,'exec'),m.__dict__);return m
pc=module('scripts/ci/process_contracts.py');scope=module('scripts/ci/product_scope.py')
policy=data(H,pc.POLICY_PATH);pc.validate_policy(policy)
count=lambda p:[len(p['files']),len(p['suites']),sum(len(s['cases']) for s in p['suites'].values())]
assert count(policy)==[279,29,1701]
rows={}
for line in git('ls-tree','-r',H).decode().splitlines():
 meta,name=line.split('\t',1);mode,kind,oid=meta.split();rows[name]=(mode,kind,oid)
for path,digest in policy['files'].items():
 assert rows[path][:2] in [('100644','blob'),('100755','blob')]
 assert hashlib.sha256(blob(H,path)).hexdigest()==digest,path
retained=[]
for label,ref in [('BASE',BASE),('accepted10c',ACCEPTED),('originalSOURCE0151',OLD)]:
 old=data(ref,pc.POLICY_PATH)
 assert old['files'].keys()<=policy['files'].keys()
 for name,suite in old['suites'].items():
  now=policy['suites'][name]
  assert all(now[k]==suite[k] for k in ['report','format','exact'])
  assert set(suite['cases'])<=set(now['cases'])
 retained.append({'label':label,'ref':ref,'counts':count(old)})
product_delta_from_accepted=[p for p in git('diff','--name-only',ACCEPTED,H).decode().splitlines() if scope.product_path(p)]
assert product_delta_from_accepted==['backend/app/services/fbs_stock_publish_service.py','frontend/src/test-contracts/inbound684586Harness.tsx']
assert blob(H,product_delta_from_accepted[0])==blob(BASE,product_delta_from_accepted[0])
assert blob(H,product_delta_from_accepted[1])==blob('a0261518f5d292e7f178f1e59ad1d20ec10a051e',product_delta_from_accepted[1])
assert [p for p in git('diff','--name-only',P,H).decode().splitlines() if scope.product_path(p)]==[]
new_tests='scripts/ci/tests/test_reviewed_process_upgrade.py'
assert blob(H,new_tests)==blob('d4533f2d290ac2379dcd097a9abffcbd3c4798d3',new_tests)
target='docs/evidence/WMS-652/reviewed-process-upgrade-20261007/'
xml=blob(H,target+'targeted.xml');actual=pc.junit_results(xml)
required=[case for case in policy['suites']['ci-shards']['cases'] if 'test_reviewed_process_upgrade.' in case]
assert len(required)==5 and all(actual.get(case)=='passed' for case in required)
for name in ['README.md','targeted.log','targeted.xml']:(HERE/('author-'+name)).write_bytes(blob(H,target+name))
workflow=yaml.safe_load(blob(H,'.github/workflows/ci.yml'))['jobs']
assert 'wms686-mockup' in workflow['process-proof']['needs']
proof=next(s for s in workflow['process-proof']['steps'] if s.get('name')=='Verify every required named case and bind evidence to this attempt')['run']
guard=next(s for s in workflow['guards']['steps'] if s.get('name')=='Preserve accepted process tests, fixtures and execution commands')['run']
for code in [guard,proof]:
 assert 'git show origin/main:scripts/ci/trusted_process_check.py' in code
 assert 'git show origin/main:scripts/ci/process_bootstrap.json' in code
 assert "pin['base_sha'] == sys.argv[2]" in code
 assert 'git show "$PROTECTED_REF:scripts/ci/process_contracts.py"' in code
 assert '--root "$GITHUB_WORKSPACE" --' in code
 subprocess.run(['bash','-n'],input=code.encode(),check=True)
assert 'git show "$PROTECTED_REF:scripts/ci/build_process_proof.py"' in proof
assert '"$TRUSTED/build_process_proof.py" --root "$GITHUB_WORKSPACE"' in proof
batch=policy['suites']['postgres-wms662-batch']
producer=next(s for s in workflow['backend-checks']['steps'] if s.get('name')=='WMS-662 isolated batch lock order on real PostgreSQL')
assert '--junitxml="$RUNNER_TEMP/release-postgres/662-batch.xml"' in producer['run']
assert batch['report']=='pg/662-batch.xml'
assert 'if' not in producer and 'continue-on-error' not in producer
assert not any('662-batch.xml' in s.get('run','') and ('cp ' in s['run'] or 'mv ' in s['run']) for job in workflow.values() for s in job.get('steps',[]))
# Simulate the actual retained artifact path; parse the required real JUnit ID.
report_tree=ET.Element('testsuites');suite=ET.SubElement(report_tree,'testsuite')
classname,name=batch['cases'][0].split('::',1);ET.SubElement(suite,'testcase',classname=classname,name=name)
with tempfile.TemporaryDirectory(dir=HERE) as directory:
 root=Path(directory);produced=root/'release-postgres/662-batch.xml';produced.parent.mkdir();produced.write_bytes(ET.tostring(report_tree))
 focused={'version':1,'files':{},'suites':{'postgres-wms662-batch':batch}}
 try:pc.verify_reports(focused,root)
 except ValueError as exc:missing=str(exc);assert missing=='Missing required file: pg/662-batch.xml'
 else:raise AssertionError('unexpected receipt admission')
 # Controlled hypothetical correct path proves the input case itself parses.
 expected=root/batch['report'];expected.parent.mkdir();expected.write_bytes(produced.read_bytes())
 assert pc.verify_reports(focused,root)=={'postgres-wms662-batch':batch['cases']}
result={'H':H,'P':P,'BASE':BASE,'counts':count(policy),'all_protected_git_hashes_modes_valid':True,'retained':retained,
 'product_delta_from_accepted10c':product_delta_from_accepted,'stock_matches_accepted_BASE':True,'harness_matches_own_a026_PASS':True,'H_product_diff_from_P':[],
 'new_five_contracts_byte_identical_to_precode':True,'author_required_five_raw_results':'passed','workflow_bash_syntax':'PASS guard and proof',
 'defect':{'suite':'postgres-wms662-batch','producer':'release-postgres/662-batch.xml','required':batch['report'],'replay_failure':missing,'correct_path_only_control':'PASS','product_impact':'No demonstrated business defect; deterministic process-proof blocker even when PG batch passes'},
 'activation':'REJECTED for H; specified data-only activation cannot correct required report path without an additional explicitly reviewed wiring delta'}
(HERE/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
