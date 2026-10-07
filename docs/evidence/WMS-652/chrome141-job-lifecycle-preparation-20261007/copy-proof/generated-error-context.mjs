// Focused observation only. Original CDP owns every send, reply and disposition.
const observed=new Set(['Fetch.requestPaused','Network.requestWillBeSent',
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
    generation:p.generation,caseId:p.caseId,cancellation:p.cancellation?
      {canceled:p.cancellation.canceled,errorText:p.cancellation.errorText,type:p.cancellation.type}:undefined};
}
// JSON escaping needs at most six bytes per UTF-16 code unit. Fixed overhead
// overestimates keys/numbers/punctuation; there is no event serialization here.
function upperBytes(value){
  if(typeof value==='string')return 2+6*value.length;
  if(value && typeof value==='object'){
    let size=64;
    // All keys are fixed ASCII allowlist names or numeric array indices.
    for(const key in value)if(value[key]!==undefined)size+=key.length+4+upperBytes(value[key]);
    return size;
  }
  return 32;
}
export function createErrorContextObserver({maxEvents=100000,maxBytes=64*1024*1024}={}){
  const budget=maxBytes-Math.min(65536,Math.floor(maxBytes/2));
  const events=[],paused=new Map(),network=new Map(),frames=new Map(),boundaries=[];
  const dropped={events:0,bytes:0,finalSize:0,observerErrors:0,nativeErrors:0};
  let estimatedBytes=0,seen=0,nativeErrorsObserved=0;
  function record(c,value){
    seen++;
    const line={utcMs:Date.now(),currentGeneration:c?.generation,currentCaseId:c?.currentCase(),...value};
    const size=upperBytes(line);
    if(events.length>=maxEvents){dropped.events++;if(value.kind==='native-error-context')dropped.nativeErrors++;return;}
    if(estimatedBytes+size>budget){dropped.bytes++;if(value.kind==='native-error-context')dropped.nativeErrors++;return;}
    const index=events.length;events.push(line);estimatedBytes+=size;return index;
  }
  function index(map,key,i){if(key!==undefined){const list=map.get(key)??[];list.push(i);map.set(key,list);}}
  return {
    message(c,msg){
      // Successful native replies and Runtime evaluation require no extra work.
      if(msg.id && !msg.error)return;
      if(!msg.id && !observed.has(msg.method))return;
      try{
        if(msg.id){
          nativeErrorsObserved++;
          const p=c.pending.get(msg.id),send=c.transport?.findLast(r=>r.kind==='command-send'&&r.commandId===msg.id);
          const key=p?.identity?.requestId,n=p?.identity?.networkId,f=p?.identity?.frameId;
          record(c,{kind:'native-error-context',commandId:msg.id,method:p?.method,
            pendingIdentity:identity(p?.identity),send:send?
              {utcMs:send.utcMs,commandId:send.commandId,method:send.method,...identity(send),attempt:send.attempt}:undefined,
            nativeError:{code:msg.error.code,message:msg.error.message},
            pausedRecordIndices:[...paused.get(key)??[]],networkRecordIndices:[...network.get(n)??[]],
            frameBoundaryIndices:[...frames.get(f)??[]],contextBoundaryIndices:[...boundaries]});
        }else{
          const p=msg.params??{},r=p.request??{},f=p.frame??{};
          const i=record(c,{kind:'protocol-context',method:msg.method,requestId:p.requestId,
            networkId:p.networkId,frameId:p.frameId??f.id,loaderId:p.loaderId??f.loaderId,
            ...safeUrl(r.url??f.url),requestMethod:r.method,resourceType:p.resourceType,
            redirectedRequestId:p.redirectedRequestId,type:p.type,
            initiator:msg.method==='Network.requestWillBeSent'?
              {type:p.initiator?.type,requestId:p.initiator?.requestId}:undefined,
            canceled:p.canceled,errorText:p.errorText,blockedReason:p.blockedReason,
            browserTimestamp:p.timestamp,browserWallTime:p.wallTime});
          if(i===undefined)return;
          if(msg.method==='Fetch.requestPaused')index(paused,p.requestId,i);
          else if(msg.method.startsWith('Network.'))index(network,p.requestId,i);
          else if(msg.method==='Page.frameNavigated')index(frames,f.id,i);
          else boundaries.push(i);
        }
      }catch{dropped.observerErrors++;}
    },
    serialize(c,report){
      // Serialization and exact byte validation happen only after the43-case run.
      const data={mode:'focused-error-context',limits:{maxEvents,maxBytes},accounting:'conservative upper bound; exact final file validation',
        seen,estimatedRetainedBytes:estimatedBytes,nativeErrorsObserved,dropped,
        pendingCommandIds:[...c?.pending.keys()??[]],completion:report?
          {status:report.status,cases:report.cases.map(x=>({id:x.id,status:x.status}))}:null,events};
      let text=JSON.stringify(data);
      while(Buffer.byteLength(text)>maxBytes && events.length){
        const removed=events.pop();dropped.finalSize++;if(removed.kind==='native-error-context')dropped.nativeErrors++;
        text=JSON.stringify(data);
      }
      if(Buffer.byteLength(text)>maxBytes)throw Error('Focused metadata summary exceeds final byte cap');
      return text;
    },
  };
}
