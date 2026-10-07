// Independent immutable fixture audit and focused helper binding probe, not 12-case rerun.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const vm = require('node:vm');
const ts = require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript');
const C = 'e2b9880d77ba2a073b325770d3e879833b02943e';
const E = 'ca6d86bd994b87b87ab9ffd878008cbbdf251860';
const git = (...args) => cp.execFileSync('git',args).toString();
const read = (ref,p) => git('show',`${ref}:${p}`);
const parent = git('rev-parse',C+'^').trim();
const base = 'docs/evidence/WMS-652/native-formatter-fixture-pending-20261007/';
const files = ['native-errors','peer-drain'].map(n=>`frontend/tests-e2e/wms672-${n}.test.mjs`);
assert.deepEqual(git('diff','--name-only',parent,C).trim().split('\n'),files);
assert.equal(git('rev-parse',E+'^').trim(),C);
const parse=(file,s)=>ts.createSourceFile(file,s,ts.ScriptTarget.Latest,true);
const calls = (source,predicate) => {const tree=parse('test.mjs',source), found=[];function visit(n){if(ts.isCallExpression(n)&&predicate(n,tree))found.push(n.getText(tree));ts.forEachChild(n,visit);}visit(tree);return found;};
const preserved=[];
for(const file of files){
 const a=read(parent,file), b=read(C,file);
 const tests=s=>calls(s,(n,t)=>n.expression.getText(t)==='test');
 assert.deepEqual(tests(b),tests(a));
 const asserts=s=>calls(s,(n,t)=>n.expression.getText(t).startsWith('assert.'));
 const old=asserts(a),now=asserts(b);
 assert.equal(now.length,old.length+1);
 assert.deepEqual(now.filter(x=>x!=="assert.ok(receiptFormatter, 'actual inbound receipt date formatter required')"),old);
 for(const expected of ['w.eval(compile(documentDisplaySource));','w.formatHumanDocumentNumber = exports.formatHumanDocumentNumber;','w.eval(compile(`globalThis.inboundReceiptDate = ${receiptFormatter.getText(tree)};`));']) assert.ok(b.includes(expected));
 preserved.push({file,unchanged_test_calls:tests(a).length,all_original_assertions:old.length,new_assertions:1});
}
const raster='frontend/tests-e2e/wms672-raster-resource.test.mjs';
assert.equal(read(parent,raster),read(C,raster));
const screen='frontend/src/screens/ff/FfInboundRequestView.tsx',display='frontend/src/screens/ff/documentDisplay.ts',utility='frontend/src/utils/printBarcodeLabel.ts';
for(const p of [screen,display,utility,'guards/PROCESS_CONTRACTS.json'])assert.equal(read(parent,p),read(C,p));
const tree=parse('screen.tsx',read(C,screen));let date;
function visit(n){if(ts.isFunctionDeclaration(n)&&n.name?.text==='inboundReceiptDate')date=n;ts.forEachChild(n,visit);}visit(tree);assert.ok(date);
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
const context=vm.createContext({exports:{}});
assert.throws(()=>vm.runInContext("formatHumanDocumentNumber({display_number:'№000672'})",context),/formatHumanDocumentNumber is not defined/);
vm.runInContext(compile(read(C,display)),context);
context.formatHumanDocumentNumber=context.exports.formatHumanDocumentNumber;
vm.runInContext(compile(`globalThis.inboundReceiptDate = ${date.getText(tree)};`),context);
assert.equal(context.formatHumanDocumentNumber,context.exports.formatHumanDocumentNumber);
assert.equal(context.formatHumanDocumentNumber({display_number:' №000672 ',document_number:'INB-99'}),'№000672');
assert.equal(context.formatHumanDocumentNumber({document_number:'INB-672'}),'№000672');
assert.equal(context.formatHumanDocumentNumber(null),null);
assert.equal(context.inboundReceiptDate('2026-10-06T12:00:00Z'),'06.10.2026');
assert.equal(context.inboundReceiptDate('2026-10-06T22:00:00Z'),'07.10.2026');
assert.equal(context.inboundReceiptDate('2026-10-06T12:00:00'),'06.10.2026');
assert.equal(context.inboundReceiptDate('invalid'),'—');
assert.equal(context.inboundReceiptDate(null),'—');
const tap=read(E,base+'native672-real-formatter-binding.tap');
const status=JSON.parse(read(E,base+'status.json'));
assert.equal(crypto.createHash('sha256').update(tap).digest('hex'),status.raw_sha256);
const titles=[...tap.matchAll(/^ok \d+ - (.+)$/gm)].map(x=>x[1]);
assert.equal(titles.length,12);assert.equal(new Set(titles).size,12);
assert.match(tap,/# pass 12\n# fail 0\n# cancelled 0\n# skipped 0/);
const policy=JSON.parse(read(C,'guards/PROCESS_CONTRACTS.json'));
const suites=['print-672-native-errors','print-672-peer-drain','print-672-raster-resource'];
const ids=suites.flatMap(n=>policy.suites[n].cases);
assert.deepEqual([...titles].sort(),[...ids].sort());
for(const n of suites){assert.equal(policy.suites[n].format,'node-tap');assert.equal(policy.suites[n].exact,true);}
for(const name of ['actual-cause.log','status.json','native672-real-formatter-binding.tap'])fs.writeFileSync(path.join(__dirname,name),read(E,base+name));
const result={pure_fixture_commit:C,evidence_commit:E,parent,etalon:git('rev-parse','origin/etalon').trim(),preserved,
 product_and_policy_bytes_unchanged:true,raster_bytes_unchanged:true,own_helper_probe:'PASS missing-global negative; actual exported helper identity; preferred/fallback/null; date UTC/Moscow/no-zone/invalid/null',
 author_raw_tap:{sha256:status.raw_sha256,passed:12,failed:0,skipped:0,exact_policy_ids:ids},
 limits:'Own focused Node VM helper probe and immutable audit only; author 12-case execution not duplicated; no browser/fullCI/SOURCE approval'};
fs.writeFileSync(path.join(__dirname,'audit.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
