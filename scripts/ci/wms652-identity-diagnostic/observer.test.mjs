import test from 'node:test';
import assert from 'node:assert/strict';
import { createObserver } from './observer.mjs';

const context = () => ({generation:7,currentCase:()=> 'synthetic-case',pending:new Map()});
test('paused identity and initiator allowlist are observed without mutating ingress', () => {
  const o=createObserver(), c=context();
  const msg={method:'Fetch.requestPaused',params:{requestId:'F1',networkId:'N1',frameId:'X',resourceType:'Fetch',redirectedRequestId:'F0',request:{url:'http://127.0.0.1:16686/api/synthetic?q=1',method:'OPTIONS',headers:{Authorization:'DO_NOT_EMIT'},postData:'DO_NOT_EMIT'}}};
  const before=JSON.stringify(msg);o.message(c,msg);
  o.message(c,{method:'Network.requestWillBeSent',params:{requestId:'N1',frameId:'X',loaderId:'L1',type:'Fetch',request:msg.params.request,initiator:{type:'preflight',requestId:'N0',stack:{secret:'DO_NOT_EMIT'}}}});
  const r=o.snapshot(c);
  assert.equal(JSON.stringify(msg),before);assert.equal(r.events[0].url,msg.params.request.url);
  assert.equal(r.events[0].requestMethod,'OPTIONS');assert.equal(r.events[0].redirectedRequestId,'F0');
  assert.deepEqual(r.events[1].initiator,{type:'preflight',requestId:'N0'});
  assert(!JSON.stringify(r).includes('DO_NOT_EMIT'));
  assert(Number.isFinite(r.events[0].nodeMonoMs));assert.equal(r.events[0].generation,7);
});
test('native success/error identity captured before pending removal; no arbitrary results', () => {
  const o=createObserver(),c=context();
  c.pending.set(9,{method:'Fetch.fulfillRequest',identity:{requestId:'F1',networkId:'N1',frameId:'X',generation:7,caseId:'synthetic-case'}});
  o.sent(c,9,'Fetch.fulfillRequest',{requestId:'F1',body:'DO_NOT_EMIT',responseHeaders:[{value:'DO_NOT_EMIT'}]});
  o.message(c,{id:9,error:{code:-32602,message:'Invalid InterceptionId.',data:'DO_NOT_EMIT'}});
  assert.equal(c.pending.size,1);assert.equal(o.snapshot(c).events[1].requestId,'F1');
  c.pending.set(10,{method:'Runtime.evaluate',identity:{}});o.message(c,{id:10,result:{result:{value:'DO_NOT_EMIT'}}});
  c.pending.set(11,{method:'Fetch.fulfillRequest',identity:{requestId:'F2'}});o.message(c,{id:11,result:{}});
  const r=o.snapshot(c);assert(!JSON.stringify(r).includes('DO_NOT_EMIT'));
  assert.equal(r.events[3].outcome,'success');assert.deepEqual(r.events[3].nativeResult,{});
});
test('event/byte caps count drops while completion and pending state survive', () => {
  const c=context(),o=createObserver({maxEvents:2,maxBytes:65536});
  for(let i=0;i<5;i++)o.message(c,{method:'Network.loadingFinished',params:{requestId:`N${i}`}});
  c.pending.set(3,{});const r=o.snapshot(c,{status:'FAIL',cases:[{id:'case',status:'FAIL'}]});
  assert.equal(r.events.length,2);assert.equal(r.dropped.events,3);assert.deepEqual(r.pendingCommandIds,[3]);assert.equal(r.completion.status,'FAIL');
  const tiny=createObserver({maxBytes:1});tiny.message(c,{method:'Network.loadingFailed',params:{requestId:'N',canceled:true,errorText:'net::ERR_ABORTED'}});
  assert.equal(tiny.snapshot(c).dropped.bytes,1);assert.equal(tiny.snapshot(c).events.length,0);
});
test('non-synthetic/auth URLs and unobserved data never enter telemetry', () => {
  const o=createObserver(),c=context();
  for(const url of ['https://customer.invalid/private?token=DO_NOT_EMIT','http://user:DO_NOT_EMIT@127.0.0.1:16686/a','http://127.0.0.1:16686/a?token=DO_NOT_EMIT'])o.message(c,{method:'Fetch.requestPaused',params:{requestId:'F',request:{url,method:'GET'}}});
  o.message(c,{method:'Runtime.consoleAPICalled',params:{data:'DO_NOT_EMIT'}});
  const r=o.snapshot(c);assert.equal(r.events.length,3);assert(!JSON.stringify(r).includes('DO_NOT_EMIT'));assert(r.events.every(e=>e.urlOmitted===true));
});
