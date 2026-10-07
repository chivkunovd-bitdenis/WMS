const errors=[];

// Bounded metadata observation, no headers/bodies or altered protocol outcomes.
const lifecycle=[], commandMetadata=new Map(); let lifecycleDropped=0;
function observe(kind,data={}){try{const utc=Date.now(),mono=performance.now();if(lifecycle.length<20000)lifecycle.push({kind,nodeUtcMs:utc,nodeUtc:new Date(utc).toISOString(),nodeMonoMs:mono,nodeTimeOriginMs:performance.timeOrigin,...data});else lifecycleDropped++;}catch{lifecycleDropped++;}}
function fields(p={}){return {requestId:p.requestId,networkId:p.networkId,frameId:p.frameId,loaderId:p.loaderId,url:p.request?.url??p.frame?.url??p.url,requestMethod:p.request?.method,responseCode:p.responseCode,errorReason:p.errorReason,browserTimestamp:p.timestamp,browserWallTime:p.wallTime,canceled:p.canceled,errorText:p.errorText,blockedReason:p.blockedReason,type:p.type,contextId:p.executionContextId,uniqueContextId:p.executionContextUniqueId,frame:p.frame?{id:p.frame.id,parentId:p.frame.parentId,loaderId:p.frame.loaderId,url:p.frame.url}:undefined};}
const observedEvents=new Set(['Fetch.requestPaused','Network.requestWillBeSent','Network.loadingFailed','Network.loadingFinished','Page.frameNavigated','Page.frameDetached','Page.frameStartedLoading','Page.frameStoppedLoading','Runtime.executionContextDestroyed','Runtime.executionContextsCleared']);

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.next = 0; this.pending = new Map(); this.listeners = new Map();
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if(msg.id){const meta=commandMetadata.get(msg.id);observe('command-result',{commandId:msg.id,...meta,error:msg.error,result:meta?.method==='Browser.getVersion'?msg.result:undefined});commandMetadata.delete(msg.id);}else if(observedEvents.has(msg.method))observe('protocol-event',{method:msg.method,...fields(msg.params)});
      if (msg.id) { const p = this.pending.get(msg.id); this.pending.delete(msg.id); if (p) { clearTimeout(p.timer); msg.error ? p.reject(Error(JSON.stringify(msg.error))) : p.resolve(msg.result); } }
      else for (const f of this.listeners.get(msg.method) ?? []) Promise.resolve(f(msg.params)).catch(e => {observe('listener-rejection',{method:msg.method,...fields(msg.params),error:String(e)});return errors.push(String(e));});
    };
  }
  async send(method, params = {}) {
    await this.ready; const id = ++this.next;
    const metadata={method,...fields(params)};commandMetadata.set(id,metadata);observe('command-send',{commandId:id,...metadata});
    return new Promise((resolve, reject) => { const timer = setTimeout(() => { this.pending.delete(id); observe('command-timeout',{commandId:id,...commandMetadata.get(id)});reject(Error(`CDP timeout ${method}`)); }, 12000); this.pending.set(id, { resolve, reject, timer }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  on(method, callback) { this.listeners.set(method, [...this.listeners.get(method) ?? [], callback]); }
}

export {CDP,observe,lifecycle,lifecycleDropped,errors};
