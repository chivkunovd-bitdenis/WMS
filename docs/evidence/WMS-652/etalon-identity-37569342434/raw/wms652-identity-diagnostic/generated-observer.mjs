// Observation only. Never send, await, classify, resolve/reject or alter a CDP object.
const eventsToObserve=new Set(['Fetch.requestPaused','Network.requestWillBeSent',
  'Network.loadingFailed','Network.loadingFinished','Page.frameNavigated',
  'Runtime.executionContextsCleared']);
function safeUrl(url){
  if(typeof url!=='string')return {};
  try{
    const u=new URL(url);
    if(['http://127.0.0.1:16686','http://127.0.0.1:17843'].includes(u.origin)
      && !u.username && !u.password && !u.hash
      && ![...u.searchParams.keys()].some(k=>/token|auth|secret|password|customer/i.test(k)))return {url};
    if(url==='about:blank')return {url};
  }catch{}
  return {urlOmitted:true};
}
function identity(p={}){
  return {requestId:p.requestId,networkId:p.networkId,frameId:p.frameId,
    generation:p.generation,caseId:p.caseId};
}
export function createObserver({maxEvents=100000,maxBytes=64*1024*1024}={}){
  // Reserve summary space inside the file cap; the event array is the log budget.
  const eventByteBudget=maxBytes-Math.min(65536,Math.floor(maxBytes/2));
  const events=[],dropped={events:0,bytes:0,observerErrors:0};let bytes=0,seen=0;
  function record(c,value){
    try{
      seen++;
      const utc=Date.now(),line={nodeUtcMs:utc,nodeUtc:new Date(utc).toISOString(),
        nodeMonoMs:performance.now(),nodeTimeOriginMs:performance.timeOrigin,
        generation:c?.generation,caseId:c?.currentCase(),...value,
        currentGeneration:c?.generation,currentCaseId:c?.currentCase()};
      const size=Buffer.byteLength(JSON.stringify(line))+1;
      if(events.length>=maxEvents){dropped.events++;return;}
      if(bytes+size>eventByteBudget){dropped.bytes++;return;}
      events.push(line);bytes+=size;
    }catch{dropped.observerErrors++;}
  }
  return {
    message(c,msg){
      try{
        if(msg.id){
          const p=c.pending.get(msg.id);
          // CDP results may contain rendered/customer data: only empty native Fetch
          // replies and navigation identity are allowed, never Runtime.evaluate data.
          const result=msg.result;
          const nativeResult=!msg.error && p?.method?.startsWith('Fetch.') && result
            && Object.keys(result).length===0 ? {} : undefined;
          record(c,{kind:'native-result',commandId:msg.id,method:p?.method,...identity(p?.identity),
            outcome:msg.error?'error':'success',nativeError:msg.error?{code:msg.error.code,message:msg.error.message}:undefined,
            nativeResult,nativeNavigation:p?.method==='Page.navigate'&&result?
              {frameId:result.frameId,loaderId:result.loaderId,errorText:result.errorText}:undefined});
        }else if(eventsToObserve.has(msg.method)){
          const p=msg.params??{},r=p.request??{},f=p.frame??{};
          record(c,{kind:'protocol-event',method:msg.method,requestId:p.requestId,
            networkId:p.networkId,frameId:p.frameId??f.id,loaderId:p.loaderId??f.loaderId,
            ...safeUrl(r.url??f.url),requestMethod:r.method,resourceType:p.resourceType,
            redirectedRequestId:p.redirectedRequestId,type:p.type,
            initiator:msg.method==='Network.requestWillBeSent'?
              {type:p.initiator?.type,requestId:p.initiator?.requestId}:undefined,
            canceled:p.canceled,errorText:p.errorText,blockedReason:p.blockedReason,
            browserTimestamp:p.timestamp,browserWallTime:p.wallTime});
        }
      }catch{dropped.observerErrors++;}
    },
    sent(c,id,method,params){
      try{
        const p=c.pending.get(id);
        record(c,{kind:'native-send',commandId:id,method,...identity(p?.identity),
          requestId:params.requestId, ...safeUrl(method==='Page.navigate'?params.url:undefined),
          responseCode:params.responseCode,errorReason:params.errorReason});
      }catch{dropped.observerErrors++;}
    },
    timedOut(c,id,method){record(c,{kind:'native-timeout',commandId:id,method,...identity(c.pending.get(id)?.identity)});},
    snapshot(c,report){return {limits:{maxEvents,maxBytes,eventByteBudget},seen,retained:events.length,retainedJsonlBytes:bytes,
      dropped,pendingCommandIds:[...c?.pending.keys()??[]],completion:report?
        {status:report.status,cases:report.cases.map(x=>({id:x.id,status:x.status}))}:null,events};},
  };
}
