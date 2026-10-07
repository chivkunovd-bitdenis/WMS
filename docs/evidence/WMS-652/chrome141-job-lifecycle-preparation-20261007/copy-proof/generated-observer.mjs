// Observation only: auxiliary negative IDs never enter the original driver maps.
import { createErrorContextObserver } from './error-context.mjs';
const workspace='http://127.0.0.1:16686/api/operations/fbs-supplies/wb-a/workspace';
const aliveMessage='Can only get response body on HeadersReceived pattern matched requests.';
function upperBytes(v){
  if(typeof v==='string')return 2+6*v.length;
  if(v && typeof v==='object'){let n=64;for(const k in v)if(v[k]!==undefined)n+=k.length+4+upperBytes(v[k]);return n;}
  return 32;
}
function urlFields(url){
  if(typeof url!=='string')return {};
  try{const u=new URL(url);if(['http://127.0.0.1:16686','http://127.0.0.1:17843'].includes(u.origin)
    && !u.username && !u.password && !u.hash && ![...u.searchParams.keys()].some(k=>/token|auth|secret|password|customer/i.test(k)))return {url};
    if(url==='about:blank')return {url};}catch{}
  return {urlOmitted:true};
}
export function createJobLookupObserver({maxEvents=100000,maxBytes=64*1024*1024}={}){
  const ownCap=Math.min(5000,Math.floor(maxEvents/2)),ownBytes=Math.floor(maxBytes/2);
  const focused=createErrorContextObserver({maxEvents:maxEvents-ownCap,maxBytes:maxBytes-ownBytes});
  const events=[],pending=new Map(),queried=new Set();
  const counts={auxSends:0,auxReplies:0,auxNativeErrors:0,ALIVE:0,ABSENT:0,unexpected:0,duplicatePaused:0,unownedReplies:0};
  const dropped={events:0,bytes:0,finalSize:0,observerErrors:0,unsent:0};
  let next=0,bytes=0;
  function record(c,value){
    const row={utcMs:Date.now(),currentGeneration:c.generation,currentCaseId:c.currentCase(),...value};
    // Reserve a second send-row estimate for its bounded pending identity copy.
    const size=upperBytes(row)*(value.kind==='aux-lookup-send'?2:1);
    if(events.length>=ownCap){dropped.events++;return;}
    if(bytes+size>ownBytes-Math.min(16384,Math.floor(ownBytes/2))){dropped.bytes++;return;}
    const i=events.length;events.push(row);bytes+=size;return i;
  }
  return {
    observerFailure(){dropped.observerErrors++;},
    message(c,msg){
      try{
        if(msg.id<0){
          const q=pending.get(msg.id);
          if(!q){counts.unownedReplies++;return;}
          pending.delete(msg.id);counts.auxReplies++;
          if(msg.error)counts.auxNativeErrors++;
          const state=msg.error?.code===-32000 && msg.error.message===aliveMessage?'ALIVE':
            msg.error?.code===-32602 && msg.error.message==='Invalid InterceptionId.'?'ABSENT':'unexpected';
          counts[state]++;
          // Never copy native error data, a result or a response body.
          record(c,{kind:'aux-lookup-reply',commandId:msg.id,requestId:q.requestId,sendIndex:q.sendIndex,state,
            sendIdentity:q.identity,nativeError:state==='unexpected'?undefined: {code:msg.error.code,message:msg.error.message},
            unexpectedErrorCode:state==='unexpected'?msg.error?.code:undefined,
            unexpectedErrorMessageOmitted:state==='unexpected'&&!!msg.error,unexpectedSuccess:state==='unexpected'&&!msg.error});
          return;
        }
        focused.message(c,msg);
        if(msg.id){
          const p=c.pending.get(msg.id);
          if(p?.method==='Page.navigate')record(c,{kind:'navigate-reply',commandId:msg.id,
            sendIdentity:{generation:p.identity?.generation,caseId:p.identity?.caseId},
            frameId:msg.result?.frameId,loaderId:msg.result?.loaderId,errorText:msg.result?.errorText});
          return;
        }
        const p=msg.params??{},x=p.context??{},a=x.auxData??{},f=p.frame??{};
        if(msg.method==='Runtime.executionContextCreated')record(c,{kind:'document-context',method:msg.method,
          executionContextId:x.id,executionContextUniqueId:x.uniqueId,frameId:a.frameId,isDefault:a.isDefault,type:a.type});
        else if(msg.method==='Runtime.executionContextDestroyed')record(c,{kind:'document-context',method:msg.method,
          executionContextId:p.executionContextId,executionContextUniqueId:p.executionContextUniqueId});
        else if(msg.method==='Runtime.executionContextsCleared')record(c,{kind:'document-context',method:msg.method});
        else if(msg.method==='Page.frameNavigated')record(c,{kind:'document-context',method:msg.method,
          frameId:f.id,parentId:f.parentId,loaderId:f.loaderId,type:p.type,...urlFields(f.url)});
        if(msg.method!=='Fetch.requestPaused' || p.request?.url!==workspace || p.request.method!=='GET'
          || p.resourceType!=='XHR' || p.networkId!==undefined || typeof p.requestId!=='string' || !p.requestId)return;
        if(queried.has(p.requestId)||c.paused.has(p.requestId)){counts.duplicatePaused++;return;}
        const id=--next,identity={requestId:p.requestId,frameId:p.frameId,generation:c.generation,caseId:c.currentCase()};
        const sendIndex=record(c,{kind:'aux-lookup-send',commandId:id,method:'Fetch.getResponseBody',...identity,
          url:workspace,requestMethod:'GET',resourceType:'XHR',redirectedRequestId:p.redirectedRequestId});
        if(sendIndex===undefined){dropped.unsent++;return;}
        queried.add(p.requestId);pending.set(id,{requestId:p.requestId,sendIndex,identity});
        // No await, original command counter, pending map, token or attempt mutation.
        try{c.ws.send(JSON.stringify({id,method:'Fetch.getResponseBody',params:{requestId:p.requestId}}));counts.auxSends++;}
        catch{pending.delete(id);dropped.unsent++;dropped.observerErrors++;}
      }catch{dropped.observerErrors++;}
    },
    serialize(c,report){
      const original=JSON.parse(focused.serialize(c,report));
      const data={mode:'exact-id-job-lookup',limits:{maxEvents,maxBytes},focused:original,
        lookup:{counts,dropped,estimatedRetainedBytes:bytes,pending:[...pending].map(([commandId,q])=>({commandId,...q})),events}};
      let text=JSON.stringify(data);
      while(Buffer.byteLength(text)>maxBytes && events.length){events.pop();dropped.finalSize++;text=JSON.stringify(data);}
      if(Buffer.byteLength(text)>maxBytes)throw Error('Job lookup summary exceeds final byte cap');
      return text;
    },
  };
}
