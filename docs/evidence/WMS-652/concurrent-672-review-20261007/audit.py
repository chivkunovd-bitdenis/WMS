"""Independent immutable merge/policy/AST audit; no runtime suite repeats."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
C = '10c018092ab6f76928a54115eb824a64adc637be'
F = '9dae4b19f6d4dca554200e08282579414a110848'
B = '4ce7ac351cf85072fa9cfa62a7917e93f3e2a94f'
OLD = '0151a555ac429957d0eee591317cc4326e909dfd'
def git(*args): return subprocess.check_output(['git',*args])
def blob(ref,path): return git('show',f'{ref}:{path}')
def data(ref,path): return json.loads(blob(ref,path))
parent = git('rev-parse',C+'^').decode().strip()
policy_path = 'guards/PROCESS_CONTRACTS.json'
now, prior, old = [data(ref,policy_path) for ref in [C,parent,OLD]]
count = lambda p: (len(p['files']),len(p['suites']),sum(len(s['cases']) for s in p['suites'].values()))
assert count(now) == (269,27,1675)
retained=[]
for label, baseline in [('parent',prior),('SOURCE0151',old)]:
 for name,s in baseline['suites'].items():
  n=now['suites'][name]
  assert all(n[k]==s[k] for k in ['report','format','exact'])
  assert set(s['cases']) <= set(n['cases'])
 retained.append({'source':label,'count':count(baseline)})
old_ids={case for s in prior['suites'].values() for case in s['cases']}
new_ids={case for s in now['suites'].values() for case in s['cases']}
assert len(new_ids-old_ids)==27
foreign=data(F,policy_path)
for name,s in foreign['suites'].items():
 assert name in now['suites']
 assert all(now['suites'][name][k]==s[k] for k in ['report','format','exact'])
 assert set(s['cases']) <= set(now['suites'][name]['cases'])
audit_root='/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/new-9dae-preservation-audit.json'
incoming=json.loads(Path(audit_root).read_text())
assert new_ids-old_ids == {case for s in incoming['new_mandatory_cases'].values() for case in s['cases']}
files=[]
for name in ['wms672-native-errors.test.mjs','wms672-peer-drain.test.mjs','wms672-raster-resource.test.mjs']:
 p='frontend/tests-e2e/'+name; assert blob(C,p)==blob(F,p); files.append(p)
for name in ['test_prod_deploy_backup.py','test_prod_deploy_backup_gate_boundary.py']:
 p='backend/tests/'+name
 assert ast.dump(ast.parse(blob(C,p)))==ast.dump(ast.parse(blob(B,p)))
 files.append(p)
screen='frontend/src/screens/ff/FfInboundRequestView.tsx'
assert blob(C,screen)==blob(parent,screen)
printer='frontend/src/utils/printBarcodeLabel.ts'
node=r'''
const cp=require('node:child_process'),ts=require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript'),assert=require('node:assert/strict');
const [c,p,f]=process.argv.slice(1),file='frontend/src/utils/printBarcodeLabel.ts';
const read=r=>cp.execFileSync('git',['show',r+':'+file]).toString();
const extract=s=>{const tree=ts.createSourceFile(file,s,ts.ScriptTarget.Latest,true);let node;function visit(n){if(ts.isVariableDeclaration(n)&&n.name.getText(tree)==='decodeImages')node=n;ts.forEachChild(n,visit)}visit(tree);assert.ok(node);return {tree,node,start:node.getStart(tree),end:node.end};};
const a=read(c),b=read(p),foreign=read(f),x=extract(a),y=extract(b),z=extract(foreign);
const print=v=>ts.createPrinter({removeComments:true}).printNode(ts.EmitHint.Unspecified,v.node,v.tree);
assert.equal(print(x),print(z));
assert.equal(a.slice(0,x.start)+b.slice(y.start,y.end)+a.slice(x.end),b);
console.log(JSON.stringify({decoder_foreign_ast_equal:true,all_outside_decoder_parent_bytes_equal:true}));
'''
decoder=json.loads(subprocess.check_output(['node','-e',node,C,parent,F]))
workflow=blob(C,'.github/workflows/ci.yml').decode()
for name in ['native-errors','peer-drain','raster-resource']:
 assert f'node --test --test-reporter=tap frontend/tests-e2e/wms672-{name}.test.mjs > "$RUNNER_TEMP/release-print/672-{name}.tap"' in workflow
suite_reports=[s['report'] for n,s in now['suites'].items() if n.startswith('print-672-') and n not in prior['suites']]
assert set(suite_reports)=={f'print/672-{n}.tap' for n in ['native-errors','peer-drain','raster-resource']}
hash_mismatch=[p for p,h in now['files'].items() if hashlib.sha256(blob(C,p)).hexdigest()!=h]
assert hash_mismatch == ['backend/tests/test_wms662_cancellation_lock_order.py'],hash_mismatch
assert now['files'][hash_mismatch[0]]==prior['files'][hash_mismatch[0]]
product_source=blob(C,'scripts/ci/product_scope.py')
ns={};exec(product_source,ns)
product_changed=[p for p in git('diff','--name-only',parent,C).decode().splitlines() if ns['product_path'](p)]
assert product_changed==[printer]
result={'candidate':C,'parent':parent,'foreign_source':F,'policy_counts':count(now),'preserved':retained,
 'all_foreign_case_report_format_exact_bindings_retained':True,'additions':sorted(new_ids-old_ids),
 'exact_native_files':files[:3],'portable_backup_AST_identical_to':B,'decoder':decoder,'whole_inbound_unchanged':True,
 'product_changes':product_changed,'known_preexisting_pending_F6_hash':hash_mismatch,
 'all_other_protected_hashes_match':True,'runtime':'Accepted twelve cases/tsc/Ruff records reused, not rerun; next combined CI pending'}
(HERE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
