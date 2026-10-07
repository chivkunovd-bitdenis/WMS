// Immutable AST + focused wait lifecycle probe. No eleven-case DOM rerun.
const cp=require('node:child_process'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const ts=require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript');
const C='a0261518f5d292e7f178f1e59ad1d20ec10a051e',E='05788bae14880fc93171e7c48a65ff825f343415';
const git=(...a)=>cp.execFileSync('git',a).toString(),read=(r,p)=>git('show',`${r}:${p}`),parent=git('rev-parse',C+'^').trim();
const test='frontend/src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx',harness='frontend/src/test-contracts/inbound684586Harness.tsx';
assert.deepEqual(git('diff','--name-only',parent,C).trim().split('\n'),[test,harness]);
const parse=(p,s)=>ts.createSourceFile(p,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const trees=[parent,C].map(r=>parse(test,read(r,test)));
const nodes=(tree,predicate)=>{const found=[];function visit(n){if(predicate(n))found.push(n);ts.forEachChild(n,visit);}visit(tree);return found;};
const its=t=>nodes(t,n=>ts.isCallExpression(n)&&n.expression.getText(t)==='it');
const print=n=>ts.createPrinter({removeComments:true}).printNode(ts.EmitHint.Unspecified,n,trees[1]);
let added=0;
const transformed=ts.transform(trees[1],[context=>root=>ts.visitNode(root,function visit(n){
 if(ts.isExpressionStatement(n)&&n.expression.getText(trees[1]).startsWith('expect(window.__WMS_PRINT_JOB_COUNT__)')){added++;return undefined;}
 return ts.visitEachChild(n,visit,context);
})]).transformed[0];
assert.equal(added,3);
const canonical=(tree,n)=>ts.createPrinter({removeComments:true}).printNode(ts.EmitHint.Unspecified,n,tree);
assert.deepEqual(its(transformed).map(n=>canonical(transformed,n)),its(trees[0]).map(n=>canonical(trees[0],n)));
const htree=parse(harness,read(C,harness));
const wait=nodes(htree,n=>ts.isFunctionDeclaration(n)&&n.name?.text==='waitForInboundState')[0];assert.ok(wait);
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
const checks=[];
async function probe(kind){
 const controller=new AbortController(),businessError=new Error('business assertion remains RED');let attempts=0,advances=0,realTurns=0,observed=false;
 const fake=kind!=='real-success';
 const vi={isFakeTimers:()=>fake,advanceTimersByTimeAsync:async ms=>{assert.equal(ms,10);advances++;if(kind==='abort-during-turn')controller.abort(new Error('owned teardown'));if(kind==='fake-success')observed=true;}};
 const context=vm.createContext({vi,act:async fn=>fn(),setTimeout:fn=>{realTurns++;observed=true;fn();}});
 vm.runInContext(compile(wait.getText(htree)+'\nglobalThis.wait = waitForInboundState;'),context);
 if(kind==='already-aborted')controller.abort(new Error('owned teardown'));
 const pending=context.wait(()=>{attempts++;if(!observed)throw businessError;},controller.signal);
 let error;try{await pending;}catch(e){error=e;}
 if(kind.endsWith('success'))assert.equal(error,undefined);
 else if(kind==='business-failure'){assert.equal(error,businessError);assert.equal(attempts,200);assert.equal(advances,200);}
 else {assert.equal(error.message,'owned teardown');assert.equal(attempts,kind==='already-aborted'?0:1);}
 checks.push({kind,attempts,advances,realTurns,result:error?.message??'observed success'});
}
(async()=>{
 for(const k of ['fake-success','real-success','business-failure','already-aborted','abort-during-turn'])await probe(k);
 const source=read(C,harness),dispose=source.slice(source.indexOf('async dispose()'));
 assert.ok(dispose.indexOf('lifecycle.abort()')<dispose.indexOf('await Promise.allSettled([...waits])'));
 assert.ok(dispose.indexOf('await Promise.allSettled([...waits])')<dispose.indexOf('root.unmount()'));
 assert.ok(source.indexOf('frame.onload = null')<source.indexOf('frame.contentDocument!.close()'));
 const loader=nodes(htree,n=>ts.isVariableDeclaration(n)&&n.name.getText(htree)==='loadPrintFrames')[0];assert.ok(loader);
 let delivered=0,written;
 const frame={dataset:{},srcdoc:'original complete source',contentWindow:{HTMLImageElement:class {}},contentDocument:{open(){},write(value){written=value;},close(){queueMicrotask(()=>frame.onload?.());}}};
 frame.onload=function(){assert.equal(this,frame);assert.equal(written,frame.srcdoc);delivered++;};
 const loaderContext=vm.createContext({frames:[frame],Event});
 vm.runInContext(compile('globalThis.load = '+loader.initializer.getText(htree)+';'),loaderContext);
 loaderContext.load();await Promise.resolve();loaderContext.load();assert.equal(delivered,1);assert.equal(frame.onload,null);
 for(const p of ['frontend/src/screens/ff/FfInboundRequestView.tsx','frontend/src/utils/printBarcodeLabel.ts','frontend/src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx','.github/workflows/ci.yml','guards/PROCESS_CONTRACTS.json'])assert.equal(read(parent,p),read(C,p));
 const base='docs/reviews/2026-10-07-wms684-586-scope-correction/ca6-dom-clock/';const logs={};
 for(const n of ['README.md','before.log','after.log','deadline-before.log','deadline-after.log']){const b=read(E,base+n);fs.writeFileSync(path.join(__dirname,'front-'+n),b);logs[n]=crypto.createHash('sha256').update(b).digest('hex');}
 assert.match(read(E,base+'before.log'),/11 passed \(11\)/);assert.match(read(E,base+'after.log'),/11 passed \(11\)/);
 assert.match(read(E,base+'deadline-before.log'),/5 failed \| 6 skipped/);
 const after=read(E,base+'deadline-after.log');assert.match(after,/1 failed \| 4 passed \| 6 skipped/);assert.ok(!after.includes('overlapping act()'));
 const result={correction:C,evidence:E,parent,original_it_bodies_unchanged_except_three_added_job_assertions:true,product_pdf_policy_CI_unchanged:true,own_wait_probes:checks,own_onload_adapter_probe:{explicit_load_calls:2,queued_platform_load:true,delivered:1,restored_source:true},author_log_sha256:logs,limit:'Synthetic act/clock and iframe boundary for actual fixture methods only; author eleven-case DOM and fault executions inspected, not duplicated'};
 fs.writeFileSync(path.join(__dirname,'front-audit.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
