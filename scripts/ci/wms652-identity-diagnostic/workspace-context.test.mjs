import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {bindingName,newDocumentSource,createWorkspaceContextObserver} from './workspace-context.mjs';
function proxy(native,binding=()=>{},extra={}){
  const sandbox={fetch:native,URL,location:{href:'http://127.0.0.1:16686/app'},crypto:{randomUUID:()=> 'doc-serial'},[bindingName]:binding,...extra};
  vm.runInNewContext(newDocumentSource,sandbox);return sandbox.fetch;
}
const target='http://127.0.0.1:16686/api/operations/fbs-supplies/wb-a/workspace';
const context=()=>({generation:7,currentCase:()=> 'send-case',pending:new Map(),transport:[]});
const report={status:'PASS',cases:[]};
test('proxy preserves native this/args/headers/signal/input and exact native Promise; never reads body',async()=>{
  const received=[],observed=[],promise=Promise.resolve({get body(){throw Error('body read');}});
  const original=function(...args){received.push({self:this,args});return promise;};
  class FakeRequest{get url(){return target;}get body(){throw Error('body read');}get headers(){throw Error('headers read');}}
  const fetch=proxy(original,s=>observed.push(JSON.parse(s)),{Request:FakeRequest});
  const headers=new Proxy({},{get(){throw Error('headers read');}}),signal=new Proxy({},{get(){throw Error('signal read');}});
  const input=new FakeRequest(),init={headers,signal,get body(){throw Error('body read');}},self={synthetic:1};
  const result=Reflect.apply(fetch,self,[input,init]);assert.equal(result,promise);assert.equal(received.length,1);
  assert.equal(received[0].self,self);assert.equal(received[0].args[0],input);assert.equal(received[0].args[1],init);assert.equal(init.headers,headers);assert.equal(init.signal,signal);
  await promise;await Promise.resolve();assert.deepEqual(observed.map(x=>x.kind),['document','call','fulfilled']);assert.equal(observed[1].pathname,new URL(target).pathname);assert.equal(observed[1].docId,'doc-serial');
  const other=fetch('http://127.0.0.1:16686/other',init);assert.equal(other,promise);await Promise.resolve();assert.equal(observed.filter(x=>x.kind==='call').length,1);
});
test('native throws and rejected reason/Promise identity remain exact, binding failure cannot alter completion',async()=>{
  const nativeError=new TypeError('PRIVATE');const throws=proxy(()=>{throw nativeError;},()=>{throw Error('observer');});
  assert.throws(()=>throws(target),x=>x===nativeError);
  const seen=[],p=Promise.reject(nativeError),fetch=proxy(()=>p,s=>seen.push(JSON.parse(s)));assert.equal(fetch(target),p);
  await assert.rejects(p,x=>x===nativeError);await Promise.resolve();assert.equal(seen.at(-1).kind,'rejected');assert.equal(seen.at(-1).errorName,'TypeError');assert(!JSON.stringify(seen).includes('PRIVATE'));
  const ok=Promise.resolve('native'),broken=proxy(()=>ok,()=>{throw Error('observer');});assert.equal(broken(target),ok);assert.equal(await ok,'native');
  const reason=Promise.reject(nativeError),brokenReject=proxy(()=>reason,()=>{throw Error('observer');});assert.equal(brokenReject(target),reason);await assert.rejects(reason,x=>x===nativeError);
});
test('native binding context binds document/call serials; arbitrary payload and unsafe stack omitted; concurrent calls remain unassigned',()=>{
  const o=createWorkspaceContextObserver(),c=context();
  o.message(c,{method:'Runtime.executionContextCreated',params:{context:{id:10,uniqueId:'unique-10',name:'PRIVATE',auxData:{frameId:'frame',isDefault:true}}}});
  const payload={docId:'doc-serial',kind:'call',callId:1,pathname:new URL(target).pathname,moduleStack:[{pathname:'/src/screens/v2/fbsApi.ts',line:810,column:3,body:'PRIVATE'},{pathname:'/customer/PRIVATE',line:1,column:1}],headers:'PRIVATE'};
  o.message(c,{method:'Runtime.bindingCalled',params:{name:bindingName,executionContextId:10,payload:JSON.stringify(payload)}});
  o.message(c,{method:'Runtime.bindingCalled',params:{name:bindingName,executionContextId:10,payload:JSON.stringify({...payload,callId:2})}});
  o.message(c,{method:'Fetch.requestPaused',params:{requestId:'F',frameId:'frame',resourceType:'XHR',request:{url:target,method:'GET',postData:'PRIVATE',headers:'PRIVATE'}}});
  o.message(c,{method:'Runtime.bindingCalled',params:{name:bindingName,executionContextId:99,payload:'PRIVATE'}});
  const d=JSON.parse(o.serialize(c,report));assert.equal(d.counts.calls,2);assert.equal(d.pendingRetainedWorkspaceCalls.length,2);assert.equal(d.counts.bindingRejected,1);assert.equal(d.events[1].executionContextId,10);assert.equal(d.events[1].docId,'doc-serial');assert.equal(d.events[1].moduleStack.length,1);assert.equal(d.events.at(-1).requestContextOwnership,'UNKNOWN');assert(!JSON.stringify(d).includes('PRIVATE'));
});
test('collector uses exact narrow-record bytes, caps honest drops; skips unrelated Network/Runtime successes',()=>{
  const o=createWorkspaceContextObserver({maxEvents:2,maxBytes:8192}),c=context();
  for(let i=0;i<4;i++)o.message(c,{method:'Runtime.executionContextCreated',params:{context:{id:i,uniqueId:'U'+i,auxData:{frameId:'frame'}}}});
  o.message(c,{id:4,result:{body:'PRIVATE'}});o.message(c,{method:'Runtime.consoleAPICalled',params:{body:'PRIVATE'}});o.message(c,{method:'Network.requestWillBeSent',params:{request:{url:'http://127.0.0.1:16686/other',body:'PRIVATE'}}});
  const text=o.serialize(c,report),d=JSON.parse(text);assert.equal(d.events.length,2);assert.equal(d.dropped.events,2);assert.equal(d.retainedRecordBytes,d.events.reduce((n,e)=>n+Buffer.byteLength(JSON.stringify(e))+1,0));assert(Buffer.byteLength(text)<=8192);assert(!text.includes('PRIVATE'));
  const tiny=createWorkspaceContextObserver({maxBytes:4096});tiny.message(c,{method:'Runtime.executionContextCreated',params:{context:{uniqueId:'x'.repeat(5000)}}});const b=JSON.parse(tiny.serialize(c,report));assert.equal(b.events.length,0);assert.equal(b.dropped.bytes,1);
});
test('original unknown native error remains rejected with exact paused identity and current reply context; observer throw cannot consume it',async()=>{
  const source=readFileSync('frontend/tests-e2e/wms652-critical/browser.mjs','utf8'),original=source.slice(source.indexOf('class CDP {'),source.indexOf('const sleep ='));
  const hook='      try { errorContext.message(this,msg); } catch { errorContext.observerFailure(); }\n';
  const commandHook="    try { errorContext.command(this,{id,method,params,identity}); } catch { errorContext.observerFailure(); }\n",anchor="    this.record({kind:'command-send',commandId:id,method,...identity,attempt:token?.attempts});";
  const generated=original.replace('      if (msg.id) {',hook+'      if (msg.id) {').replace(anchor,commandHook+anchor);assert.equal(generated.replace(hook,'').replace(commandHook,''),original);
  class Wire{constructor(){this.sent=[];}send(x){this.sent.push(JSON.parse(x));}emit(m){this.onmessage({data:JSON.stringify(m)});}}
  const o=createWorkspaceContextObserver(),CDP=vm.runInNewContext(generated+'\nCDP',{WebSocket:Wire,report:{currentCase:'case'},errors:[],errorContext:o,setTimeout,clearTimeout});
  const c=new CDP('synthetic');c.ws.onopen();c.ws.emit({method:'Fetch.requestPaused',params:{requestId:'F',frameId:'frame',resourceType:'XHR',request:{url:target,method:'GET'}}});
  const p=c.send('Fetch.fulfillRequest',{requestId:'F'});await Promise.resolve();c.generation=8;c.ws.emit({id:1,error:{code:-32602,message:'Invalid InterceptionId.'}});await assert.rejects(p,/Invalid InterceptionId/);assert.equal(c.paused.get('F').disposition,'paused');assert.equal(c.pending.size,0);assert.equal(c.ws.sent.length,1);assert.equal(c.ws.sent[0].method,'Fetch.fulfillRequest');
  const d=JSON.parse(o.serialize(c,report)),r=d.events.at(-1);assert.equal(r.send.generation,0);assert.equal(r.currentGeneration,8);assert.equal(r.requestId,'F');assert.equal(d.counts.originalNativeErrors,1);
  let faults=0;const Throw=vm.runInNewContext(generated+'\nCDP',{WebSocket:Wire,report:{},errors:[],errorContext:{message(){throw Error('observer');},command(){throw Error('observer');},observerFailure(){faults++;}},setTimeout,clearTimeout});
  const t=new Throw('synthetic');t.ws.onopen();const strict=t.send('Fetch.fulfillRequest',{requestId:'unknown'});await Promise.resolve();t.ws.emit({id:1,error:{code:-32602,message:'Invalid InterceptionId.'}});await assert.rejects(strict,/Invalid InterceptionId/);assert.equal(faults,2);
});
test('only binding/new-document setup added; navigate/readiness identity captured without expressions or extra sends',async()=>{
  const o=createWorkspaceContextObserver(),c=context(),sends=[];c.send=async(method,params)=>{sends.push({method,params});};await o.install(c);
  assert.deepEqual(sends.map(x=>x.method),['Runtime.addBinding','Page.addScriptToEvaluateOnNewDocument']);assert(!sends.some(x=>x.method==='Fetch.getResponseBody'||x.method==='Runtime.evaluate'));
  o.command(c,{id:5,method:'Page.navigate',params:{url:target},identity:{generation:7,caseId:'nav-send'}});
  o.message(c,{id:5,result:{frameId:'frame',loaderId:'loader'}});
  o.command(c,{id:6,method:'Runtime.evaluate',params:{expression:"Boolean(document.querySelector('PRIVATE'))"},identity:{generation:7,caseId:'poll-send'}});
  c.generation=8;o.message(c,{id:6,result:{result:{value:true}}});
  const text=o.serialize(c,report),d=JSON.parse(text);assert.equal(d.events[1].loaderId,'loader');assert.equal(d.events[3].ready,true);assert.equal(d.events[3].sendIdentity.caseId,'poll-send');assert.equal(d.events[3].generation,8);assert.equal(d.pendingDocumentCommandIds.length,0);assert(!text.includes('PRIVATE'));
});
