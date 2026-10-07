import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createJobLookupObserver} from './job-lookup.mjs';
const alive='Can only get response body on HeadersReceived pattern matched requests.';
const pause=()=>({method:'Fetch.requestPaused',params:{requestId:'F1',frameId:'frame',resourceType:'XHR',request:{url:'http://127.0.0.1:16686/api/operations/fbs-supplies/wb-a/workspace',method:'GET',headers:{token:'PRIVATE'},postData:'PRIVATE'}}});
function context(){const sent=[];return {generation:7,currentCase:()=> 'send-case',paused:new Map(),pending:new Map(),transport:[],next:0,ws:{send:x=>sent.push(JSON.parse(x))},sent};}
const data=(o,c)=>JSON.parse(o.serialize(c));
test('exact owned class queries once on same wire without original state/input mutation; rejects all other classes',()=>{
  const o=createJobLookupObserver(),c=context(),m=pause(),before=structuredClone(m);
  for(const change of [{networkId:'N'}, {resourceType:'Fetch'}, {request:{...m.params.request,method:'POST'}}, {request:{...m.params.request,url:'http://127.0.0.1:16686/other'}}])o.message(c,{method:m.method,params:{...m.params,...change}});
  assert.equal(c.sent.length,0);o.message(c,m);o.message(c,m);
  assert.deepEqual(m,before);assert.equal(c.next,0);assert.equal(c.pending.size,0);assert.equal(c.paused.size,0);
  assert.deepEqual(c.sent,[{id:-1,method:'Fetch.getResponseBody',params:{requestId:'F1'}}]);
  assert.equal(data(o,c).lookup.counts.duplicatePaused,1);assert(!o.serialize(c).includes('PRIVATE'));
});
test('exact alive/absent/unexpected/unowned replies remain separate and preserve send/current identities',()=>{
  const o=createJobLookupObserver(),c=context();
  for(const [requestId,error,result] of [['F1',{code:-32000,message:alive}],['F2',{code:-32602,message:'Invalid InterceptionId.'}],['F3',{code:-32000,message:'PRIVATE'}],['F4',undefined,{body:'PRIVATE',base64Encoded:true}]]){
    const m=pause();m.params.requestId=requestId;o.message(c,m);c.generation=8;c.currentCase=()=> 'reply-case';
    o.message(c,{id:-c.sent.length,error,result});c.generation=7;c.currentCase=()=> 'send-case';
  }
  o.message(c,{id:-999,error:{code:-32602,message:'PRIVATE'}});
  const d=data(o,c);assert.deepEqual([d.lookup.counts.ALIVE,d.lookup.counts.ABSENT,d.lookup.counts.unexpected,d.lookup.counts.unownedReplies],[1,1,2,1]);
  assert.equal(d.lookup.counts.auxNativeErrors,3);assert.equal(d.focused.nativeErrorsObserved,0);assert.equal(d.lookup.pending.length,0);
  const r=d.lookup.events.find(x=>x.kind==='aux-lookup-reply');assert.equal(r.requestId,'F1');assert.equal(r.sendIdentity.generation,7);assert.equal(r.currentGeneration,8);assert.equal(r.currentCaseId,'reply-case');assert(!o.serialize(c).includes('PRIVATE'));
});
test('original driver still forwards exact success and rejects unknown first fulfill; observer throw cannot consume native reply',async()=>{
  const source=readFileSync('frontend/tests-e2e/wms652-critical/browser.mjs','utf8'),original=source.slice(source.indexOf('class CDP {'),source.indexOf('const sleep ='));
  const insertion='      try { errorContext.message(this,msg); } catch { errorContext.observerFailure(); }\n';
  const generated=original.replace('      if (msg.id) {',insertion+'      if (msg.id) {');assert.equal(generated.replace(insertion,''),original);
  class Wire{constructor(){this.sent=[];}send(raw){this.sent.push(JSON.parse(raw));}emit(msg){this.onmessage({data:JSON.stringify(msg)});}}
  const o=createJobLookupObserver(),CDP=vm.runInNewContext(generated+'\nCDP',{WebSocket:Wire,report:{currentCase:'send-case'},errors:[],errorContext:o,setTimeout,clearTimeout});
  const c=new CDP('synthetic');c.ws.onopen();c.ws.emit(pause());assert.equal(c.next,0);assert.equal(c.paused.get('F1').attempts,0);
  const p=c.send('Fetch.fulfillRequest',{requestId:'F1'});await Promise.resolve();assert.equal(c.ws.sent[0].id,-1);assert.equal(c.ws.sent[1].id,1);assert.equal(c.paused.get('F1').attempts,1);
  c.generation=8;c.ws.emit({id:-1,error:{code:-32000,message:alive}});assert.equal(c.pending.size,1);
  c.ws.emit({id:1,error:{code:-32602,message:'Invalid InterceptionId.'}});await assert.rejects(p,/Invalid InterceptionId/);assert.equal(c.paused.get('F1').disposition,'paused');
  const positive=data(o,c).focused.events.find(x=>x.kind==='native-error-context');assert.equal(positive.commandId,1);assert.equal(positive.send.generation,0);assert.equal(positive.currentGeneration,8);
  const success=c.send('Runtime.evaluate',{});await Promise.resolve();c.ws.emit({id:2,result:{value:'original'}});assert.equal(JSON.stringify(await success),'{"value":"original"}');assert.equal(data(o,c).focused.nativeErrorsObserved,1);
  let failures=0;const ThrowCDP=vm.runInNewContext(generated+'\nCDP',{WebSocket:Wire,report:{},errors:[],errorContext:{message(){throw Error('synthetic observer');},observerFailure(){failures++;}},setTimeout,clearTimeout});
  const throwing=new ThrowCDP('synthetic');throwing.ws.onopen();const strict=throwing.send('Fetch.fulfillRequest',{requestId:'unknown'});await Promise.resolve();throwing.ws.emit({id:1,error:{code:-32602,message:'Invalid InterceptionId.'}});await assert.rejects(strict,/Invalid InterceptionId/);assert.equal(failures,1);assert.equal(throwing.pending.size,0);
});
test('existing document events and navigate reply retain only allowlisted identities, no duplicate runtime/success logging',()=>{
  const o=createJobLookupObserver(),c=context();
  c.pending.set(1,{method:'Page.navigate',identity:{generation:6,caseId:'nav-send'}});
  o.message(c,{id:1,result:{frameId:'frame',loaderId:'loader',body:'PRIVATE'}});
  o.message(c,{method:'Runtime.executionContextCreated',params:{context:{id:11,uniqueId:'unique',name:'PRIVATE',origin:'PRIVATE',auxData:{frameId:'frame',isDefault:true,type:'default',secret:'PRIVATE'}}}});
  o.message(c,{method:'Runtime.executionContextDestroyed',params:{executionContextId:11,executionContextUniqueId:'unique',body:'PRIVATE'}});
  o.message(c,{method:'Runtime.executionContextsCleared',params:{body:'PRIVATE'}});
  o.message(c,{method:'Page.frameNavigated',params:{frame:{id:'frame',loaderId:'loader',url:'http://127.0.0.1:16686/app',secret:'PRIVATE'}}});
  o.message(c,{id:2,result:{body:'PRIVATE'}});o.message(c,{method:'Runtime.consoleAPICalled',params:{body:'PRIVATE'}});
  const d=data(o,c);assert.equal(d.lookup.events.length,5);assert.equal(d.lookup.events[0].loaderId,'loader');assert.equal(d.lookup.events[1].isDefault,true);assert.equal(d.lookup.events[2].executionContextUniqueId,'unique');assert(!o.serialize(c).includes('PRIVATE'));
});
test('combined event/byte caps have honest drops and pending queries; observer errors preserve ingress',()=>{
  const o=createJobLookupObserver({maxEvents:4,maxBytes:65536}),c=context();
  for(let i=0;i<8;i++){const m=pause();m.params.requestId='F'+i;o.message(c,m);}
  const text=o.serialize(c),d=JSON.parse(text);assert(d.lookup.events.length+d.focused.events.length<=4);assert(Buffer.byteLength(text)<=65536);assert.equal(d.lookup.counts.auxSends,2);assert.equal(d.lookup.pending.length,2);assert.equal(d.lookup.dropped.unsent,6);assert(d.lookup.dropped.events>0);assert(d.focused.dropped.events>0);
  const tiny=createJobLookupObserver({maxBytes:4096});tiny.message(c,{method:'Runtime.executionContextCreated',params:{context:{uniqueId:'x'.repeat(5000)}}});assert.equal(data(tiny,c).lookup.dropped.bytes,1);
  const bad={...c,currentCase(){throw Error('synthetic');}};o.message(bad,{method:'Runtime.executionContextCreated',params:{context:{id:1}}});assert.equal(data(o,c).lookup.dropped.observerErrors,1);
});
