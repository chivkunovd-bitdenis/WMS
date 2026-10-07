import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createErrorContextObserver } from './error-context.mjs';

const context=()=>({generation:7,currentCase:()=> 'send-case',pending:new Map(),transport:[]});
test('focused ingress preserves input and skips successes/Runtime without event serialization or ISO clocks',()=>{
  const o=createErrorContextObserver(),c=context();
  const msg={method:'Fetch.requestPaused',params:{requestId:'F1',networkId:'N1',frameId:'X',resourceType:'XHR',request:{url:'http://127.0.0.1:16686/api/fake',method:'GET',headers:{auth:'DO_NOT_EMIT'},postData:'DO_NOT_EMIT'}}};
  const before=structuredClone(msg),stringify=JSON.stringify,iso=Date.prototype.toISOString;
  try{
    JSON.stringify=()=>{throw Error('per-event serialization');};Date.prototype.toISOString=()=>{throw Error('per-event ISO');};
    o.message(c,msg);o.message(c,{id:9,result:{value:'DO_NOT_EMIT'}});
    o.message(c,{method:'Runtime.consoleAPICalled',params:{value:'DO_NOT_EMIT'}});
  }finally{JSON.stringify=stringify;Date.prototype.toISOString=iso;}
  assert.deepEqual(msg,before);const d=JSON.parse(o.serialize(c));
  assert.equal(d.events.length,1);assert.equal(d.events[0].url,msg.params.request.url);
  assert(!JSON.stringify(d).includes('DO_NOT_EMIT'));assert.equal(d.nativeErrorsObserved,0);
  assert(!d.events.some(r=>r.kind==='native-send'||r.kind==='native-result'));
});
test('native error retains exact pending/send/paused/lifecycle and current reply context',()=>{
  const o=createErrorContextObserver(),c=context();
  o.message(c,{method:'Fetch.requestPaused',params:{requestId:'F1',networkId:'N1',frameId:'X',resourceType:'XHR',request:{url:'http://127.0.0.1:16686/api/fake',method:'GET'}}});
  o.message(c,{method:'Network.requestWillBeSent',params:{requestId:'N1',frameId:'X',loaderId:'L1',type:'Fetch',request:{url:'http://127.0.0.1:16686/api/fake',method:'GET'},initiator:{type:'script',requestId:'N0',stack:{value:'DO_NOT_EMIT'}}}});
  o.message(c,{method:'Network.loadingFailed',params:{requestId:'N1',canceled:false,errorText:'net::ERR_CONNECTION_CLOSED',type:'Fetch'}});
  const identity={requestId:'F1',networkId:'N1',frameId:'X',generation:7,caseId:'send-case'};
  c.pending.set(9,{method:'Fetch.fulfillRequest',identity});c.transport.push({kind:'command-send',commandId:9,method:'Fetch.fulfillRequest',utcMs:100,...identity});
  c.generation=8;c.currentCase=()=> 'reply-case';
  o.message(c,{id:9,error:{code:-32602,message:'Invalid InterceptionId.',data:'DO_NOT_EMIT'}});
  const d=JSON.parse(o.serialize(c)),r=d.events.at(-1);
  assert.deepEqual(c.pending.get(9).identity,identity);assert.equal(r.commandId,9);assert.equal(r.method,'Fetch.fulfillRequest');
  assert.equal(r.send.generation,7);assert.equal(r.currentGeneration,8);assert.equal(r.currentCaseId,'reply-case');
  assert.equal(r.pendingIdentity.requestId,'F1');assert.equal(d.events[r.pausedRecordIndices[0]].requestId,'F1');
  assert.deepEqual(r.networkRecordIndices,[1,2]);assert.deepEqual(r.nativeError,{code:-32602,message:'Invalid InterceptionId.'});
  assert(!JSON.stringify(d).includes('DO_NOT_EMIT'));
});
test('actual original CDP forwarding keeps unknown native refusal strict and success exact',async()=>{
  const o=createErrorContextObserver(),source=readFileSync('frontend/tests-e2e/wms652-critical/browser.mjs','utf8');
  const original=source.slice(source.indexOf('class CDP {'),source.indexOf('const sleep ='));
  const insertion='      if (msg.error || msg.method) errorContext.message(this,msg);\n',anchor='      if (msg.id) {';
  const observed=original.replace(anchor,insertion+anchor);assert.equal(observed.replace(insertion,''),original);
  class Wire{constructor(){this.sent=[];}send(raw){this.sent.push(JSON.parse(raw));}emit(msg){this.onmessage({data:JSON.stringify(msg)});}}
  const CDP=vm.runInNewContext(observed+'\nCDP',{WebSocket:Wire,report:{currentCase:'send-case'},errors:[],errorContext:o,setTimeout,clearTimeout});
  const c=new CDP('controlled');c.ws.onopen();
  c.ws.emit({method:'Fetch.requestPaused',params:{requestId:'F1',frameId:'X',resourceType:'XHR',request:{url:'http://127.0.0.1:16686/api/fake',method:'GET'}}});
  const pending=c.send('Fetch.fulfillRequest',{requestId:'F1'});await Promise.resolve();
  c.ws.emit({id:1,error:{code:-32602,message:'Invalid InterceptionId.'}});
  await assert.rejects(pending,/Invalid InterceptionId/);assert.equal(c.paused.get('F1').disposition,'paused');
  const success=c.send('Runtime.evaluate',{});await Promise.resolve();const result={safe:'synthetic'};c.ws.emit({id:2,result});
  assert.equal(JSON.stringify(await success),JSON.stringify(result));assert.equal(c.ws.sent.length,2);assert.equal(c.pending.size,0);
  assert.equal(JSON.parse(o.serialize(c)).nativeErrorsObserved,1);
});
test('focused bounds count drops, validate final size and keep privacy allowlist',()=>{
  const c=context(),o=createErrorContextObserver({maxEvents:2,maxBytes:65536});
  for(const url of ['https://customer.invalid/?token=DO_NOT_EMIT','http://127.0.0.1:16686/a?token=DO_NOT_EMIT','http://127.0.0.1:16686/fake'])o.message(c,{method:'Fetch.requestPaused',params:{requestId:'F',request:{url,method:'GET'}}});
  const text=o.serialize(c),d=JSON.parse(text);assert.equal(d.events.length,2);assert.equal(d.dropped.events,1);assert(!text.includes('DO_NOT_EMIT'));assert(d.events.every(r=>r.urlOmitted));assert(Buffer.byteLength(text)<=65536);
  const small=createErrorContextObserver({maxBytes:2048});small.message(c,{method:'Fetch.requestPaused',params:{requestId:'F',request:{url:'http://127.0.0.1:16686/'+ 'x'.repeat(3000),method:'GET'}}});
  const bounded=small.serialize(c),b=JSON.parse(bounded);assert.equal(b.events.length,0);assert.equal(b.dropped.bytes,1);assert(Buffer.byteLength(bounded)<=2048);
});
