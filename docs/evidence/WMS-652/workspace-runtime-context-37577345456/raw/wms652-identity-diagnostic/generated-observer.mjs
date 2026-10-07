export const bindingName='__wms652WorkspaceObservation';
const targetPath='/api/operations/fbs-supplies/wb-a/workspace';
// This function runs in each new document. It never inspects headers/signal/body.
export function installWorkspaceProxy(binding){
  try{
    const native=globalThis.fetch,then=Promise.prototype.then;
    const requestUrl=typeof Request==='function'?Object.getOwnPropertyDescriptor(Request.prototype,'url')?.get:null;
    const urlHref=Object.getOwnPropertyDescriptor(URL.prototype,'href')?.get;
    const domName=typeof DOMException==='function'?Object.getOwnPropertyDescriptor(DOMException.prototype,'name')?.get:null;
    const docId=crypto.randomUUID();let serial=0;
    function emit(value){try{globalThis[binding](JSON.stringify({docId,...value}));}catch{}}
    function errorName(error){
      try{if(domName)return Reflect.apply(domName,error,[]);}catch{}
      try{let p=error;for(let i=0;p && i<4;i++,p=Object.getPrototypeOf(p)){
        const d=Object.getOwnPropertyDescriptor(p,'name');if(d && 'value' in d && typeof d.value==='string' && /^[A-Za-z]{1,40}$/.test(d.value))return d.value;
      }}catch{}return 'Unknown';
    }
    function inputUrl(input){
      if(typeof input==='string')return input;
      try{if(requestUrl)return Reflect.apply(requestUrl,input,[]);}catch{}
      try{if(urlHref)return Reflect.apply(urlHref,input,[]);}catch{}
    }
    function moduleStack(){
      try{return (new Error().stack??'').split('\n').flatMap(line=>{
        const m=line.match(/http:\/\/127\.0\.0\.1:16686(\/(?:src|assets)\/[A-Za-z0-9_./-]+)(?:\?[^\s():]*)?:(\d+):(\d+)/);
        return m?[{pathname:m[1].slice(0,200),line:Number(m[2]),column:Number(m[3])}]:[];
      }).slice(0,5);}catch{return [];}
    }
    globalThis.fetch=new Proxy(native,{apply(target,thisArg,args){
      // Invoke native exactly once first; preserve its thisArg, args and Promise.
      const result=Reflect.apply(target,thisArg,args);
      try{
        const raw=inputUrl(args[0]);if(raw===undefined)return result;
        const u=new URL(raw,location.href);
        if(u.origin!=='http://127.0.0.1:16686' || u.pathname!=='/api/operations/fbs-supplies/wb-a/workspace')return result;
        const callId=++serial;
        emit({kind:'call',callId,pathname:u.pathname,moduleStack:moduleStack()});
        Reflect.apply(then,result,[()=>{emit({kind:'fulfilled',callId});},error=>{emit({kind:'rejected',callId,errorName:errorName(error)});}]);
      }catch{}
      return result;
    }});
    emit({kind:'document'});
  }catch{}
}
export const newDocumentSource=`(${installWorkspaceProxy.toString()})(${JSON.stringify(bindingName)});`;
function target(url){if(typeof url!=='string' || !url.includes(targetPath))return false;try{const u=new URL(url);return u.origin==='http://127.0.0.1:16686' && u.pathname===targetPath;}catch{return false;}}
function identity(p={}){return {requestId:p.requestId,networkId:p.networkId,frameId:p.frameId,generation:p.generation,caseId:p.caseId};}
export function createWorkspaceContextObserver({maxEvents=100000,maxBytes=64*1024*1024}={}){
  const events=[],pendingReadiness=new Map(),paused=new Map(),network=new Set();
  const counts={calls:0,fulfilled:0,rejected:0,documents:0,paused:0,originalNativeErrors:0,bindingRejected:0};
  const dropped={events:0,bytes:0,observerErrors:0,finalSize:0};
  let retainedBytes=0;
  const budget=maxBytes-Math.min(16384,Math.floor(maxBytes/4));
  function record(c,value){
    const row={utcMs:Date.now(),generation:c.generation,caseId:c.currentCase(),...value};
    // Narrow records only: measure their real serialized size, not huge protocol payloads.
    const encoded=JSON.stringify(row),size=Buffer.byteLength(encoded)+1;
    if(events.length>=maxEvents){dropped.events++;return;}
    if(retainedBytes+size>budget){dropped.bytes++;return;}
    const i=events.length;events.push(row);retainedBytes+=size;return i;
  }
  return {
    observerFailure(){dropped.observerErrors++;},
    async install(c){await c.send('Runtime.addBinding',{name:bindingName});await c.send('Page.addScriptToEvaluateOnNewDocument',{source:newDocumentSource});},
    command(c,{id,method,params,identity:sendIdentity}){
      try{
        const readiness=method==='Runtime.evaluate' && typeof params.expression==='string'
          && params.expression.startsWith('Boolean(') && params.expression.includes('document.querySelector');
        if(method!=='Page.navigate' && !readiness)return;
        if(pendingReadiness.size<maxEvents)pendingReadiness.set(id,{method,sendIdentity:identity(sendIdentity),readiness});
        else dropped.events++;
        record(c,{kind:'document-command-send',commandId:id,method,sendIdentity:identity(sendIdentity),readiness});
      }catch{dropped.observerErrors++;}
    },
    message(c,msg){
      try{
        if(msg.id){
          const p=c.pending.get(msg.id),d=pendingReadiness.get(msg.id);
          if(d){pendingReadiness.delete(msg.id);record(c,{kind:'document-command-reply',commandId:msg.id,...d,
            frameId:msg.result?.frameId,loaderId:msg.result?.loaderId,
            ready:typeof msg.result?.result?.value==='boolean'?msg.result.result.value:undefined,nativeErrorCode:msg.error?.code});}
          if(msg.error){counts.originalNativeErrors++;const key=p?.identity?.requestId;
            const send=c.transport.findLast(r=>r.kind==='command-send'&&r.commandId===msg.id);
            record(c,{kind:'original-native-error',commandId:msg.id,method:p?.method,currentGeneration:c.generation,currentCaseId:c.currentCase(),
              pendingIdentity:identity(p?.identity),send:send?{commandId:send.commandId,utcMs:send.utcMs,method:send.method,...identity(send),attempt:send.attempt}:undefined,
              nativeError:{code:msg.error.code,message:msg.error.message},requestId:key,
              exactPausedRecordIndices:paused.get(key)??[],requestContextOwnership:'UNKNOWN'});
          }return;
        }
        const p=msg.params??{},x=p.context??{},a=x.auxData??{},f=p.frame??{};
        if(msg.method==='Runtime.bindingCalled' && p.name===bindingName){
          let v;try{if(typeof p.payload!=='string'||p.payload.length>8192)throw Error();v=JSON.parse(p.payload);}catch{counts.bindingRejected++;return;}
          if(typeof v.docId!=='string'||! /^[A-Za-z0-9-]{1,80}$/.test(v.docId)||!['document','call','fulfilled','rejected'].includes(v.kind)
            || (v.kind!=='document' && (!Number.isSafeInteger(v.callId)||v.callId<1))){counts.bindingRejected++;return;}
          if(v.kind==='call' && v.pathname!==targetPath){counts.bindingRejected++;return;}
          const stack=Array.isArray(v.moduleStack)?v.moduleStack.slice(0,5).filter(s=>typeof s.pathname==='string' && /^\/(src|assets)\/[A-Za-z0-9_./-]{1,200}$/.test(s.pathname) && Number.isSafeInteger(s.line)&&Number.isSafeInteger(s.column)).map(s=>({pathname:s.pathname,line:s.line,column:s.column})):undefined;
          counts[{document:'documents',call:'calls',fulfilled:'fulfilled',rejected:'rejected'}[v.kind]]++;
          record(c,{kind:'workspace-binding',phase:v.kind,executionContextId:p.executionContextId,docId:v.docId,callId:v.callId,
            pathname:v.kind==='call'?targetPath:undefined,moduleStack:v.kind==='call'?stack:undefined,
            errorName:v.kind==='rejected' && typeof v.errorName==='string' && /^[A-Za-z]{1,40}$/.test(v.errorName)?v.errorName:undefined});
        }else if(msg.method==='Runtime.executionContextCreated')record(c,{kind:'document-context',method:msg.method,
          executionContextId:x.id,executionContextUniqueId:x.uniqueId,frameId:a.frameId,isDefault:a.isDefault,type:a.type});
        else if(msg.method==='Runtime.executionContextDestroyed')record(c,{kind:'document-context',method:msg.method,
          executionContextId:p.executionContextId,executionContextUniqueId:p.executionContextUniqueId});
        else if(msg.method==='Runtime.executionContextsCleared')record(c,{kind:'document-context',method:msg.method});
        else if(msg.method==='Page.frameNavigated')record(c,{kind:'document-context',method:msg.method,frameId:f.id,parentId:f.parentId,loaderId:f.loaderId,type:p.type});
        else if(msg.method==='Fetch.requestPaused' && target(p.request?.url)){
          counts.paused++;const i=record(c,{kind:'workspace-paused',requestId:p.requestId,networkId:p.networkId,frameId:p.frameId,
            pathname:targetPath,resourceType:p.resourceType,requestMethod:p.request?.method,redirectedRequestId:p.redirectedRequestId,requestContextOwnership:'UNKNOWN'});
          if(i!==undefined){const indices=paused.get(p.requestId)??[];indices.push(i);paused.set(p.requestId,indices);}
        }else if(msg.method==='Network.requestWillBeSent' && target(p.request?.url)){const i=record(c,{kind:'workspace-network',requestId:p.requestId,frameId:p.frameId,loaderId:p.loaderId,type:p.type,
          pathname:targetPath,initiatorType:p.initiator?.type,initiatorRequestId:p.initiator?.requestId});if(i!==undefined)network.add(p.requestId);
        }else if(['Network.loadingFailed','Network.loadingFinished'].includes(msg.method) && network.has(p.requestId))record(c,{kind:'workspace-network-terminal',method:msg.method,requestId:p.requestId,canceled:p.canceled,errorText:p.errorText,type:p.type});
      }catch{dropped.observerErrors++;}
    },
    serialize(c,report){
      const retainedPending=new Map();
      for(const r of events)if(r.kind==='workspace-binding' && r.callId){
        const key=`${r.executionContextId}:${r.docId}:${r.callId}`;
        if(r.phase==='call')retainedPending.set(key,{executionContextId:r.executionContextId,docId:r.docId,callId:r.callId});
        else retainedPending.delete(key);
      }
      const data={mode:'passive-workspace-runtime-context',limits:{maxEvents,maxBytes},accounting:'exact UTF8 serialized narrow-record bytes; final file validation',retainedRecordBytes:retainedBytes,
        counts,dropped,pendingRetainedWorkspaceCalls:[...retainedPending.values()],pendingDocumentCommandIds:[...pendingReadiness.keys()],originalPendingCommandIds:[...c.pending.keys()],completion:{status:report.status,cases:report.cases.map(x=>({id:x.id,status:x.status}))},events};
      let text=JSON.stringify(data);
      while(Buffer.byteLength(text)>maxBytes && events.length){events.pop();dropped.finalSize++;data.pendingRetainedWorkspaceCalls=null;data.pendingWorkspaceCallsUnknownAfterFinalTrim=true;text=JSON.stringify(data);}
      if(Buffer.byteLength(text)>maxBytes)throw Error('Workspace summary exceeds byte cap');return text;
    },
  };
}
