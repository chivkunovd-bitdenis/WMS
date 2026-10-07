// Separate synthetic transport measurement, never an explanation of the old run.
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {CDP,observe,lifecycle,lifecycleDropped,errors} from './cdp-observer.mjs';
const dir=process.env.WMS652_EVIDENCE, origin='http://127.0.0.1:16686';
assert(dir&&process.env.WMS652_CHROME&&process.platform==='linux'&&process.env.GITHUB_ACTIONS==='true');
const profile=await mkdtemp(resolve(tmpdir(),'wms652-owned-explicit-abort-'));
const chrome=spawn(process.env.WMS652_CHROME,['--headless=new','--mute-audio','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--remote-debugging-port=16689',`--user-data-dir=${profile}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='',cdp;chrome.stdout.on('data',d=>chromeLog+=d);chrome.stderr.on('data',d=>chromeLog+=d);
const report={synthetic:true,originalFailureCause:'NOT_PROVEN_BY_THIS_CONTROL',status:'INCONCLUSIVE'};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function deadline(promise,ms,label){let timer;return Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error(`control deadline ${label}`)),ms))]).finally(()=>clearTimeout(timer));}
function errorDetails(error){try{return JSON.parse(error.message);}catch{return {message:String(error)};}}
try{
 let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch('http://127.0.0.1:16689/json/list')).json();break;}catch{await sleep(100);}}
 assert(tabs?.length,'separate control Chrome unavailable');cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
 const version=await cdp.send('Browser.getVersion');assert.equal(version.product,'Chrome/141.0.7390.37');report.environment={node:process.version,platform:process.platform,arch:process.arch,...version};
 await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
 let resolvePaused,resolveCanceled;const pausedPromise=new Promise(r=>resolvePaused=r),canceledPromise=new Promise(r=>resolveCanceled=r);let paused;
 cdp.on('Network.loadingFailed',e=>{if(paused&&e.requestId===paused.networkId)resolveCanceled(e);});
 cdp.on('Fetch.requestPaused',async e=>{
  const url=new URL(e.request.url);
  if(url.origin!==origin)return cdp.send('Fetch.failRequest',{requestId:e.requestId,errorReason:'BlockedByClient'});
  if(url.pathname==='/__wms652_paused_abort__'){paused={requestId:e.requestId,networkId:e.networkId,frameId:e.frameId,url:e.request.url,method:e.request.method};resolvePaused(paused);return;}
  const body=url.pathname==='/__wms652_transport_document__'?'<!doctype html><meta charset=utf-8><body>isolated transport control</body>':'';
  return cdp.send('Fetch.fulfillRequest',{requestId:e.requestId,responseCode:body?200:204,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from(body).toString('base64')});
 });
 await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
 await cdp.send('Page.navigate',{url:origin+'/__wms652_transport_document__'});
 let documentReady=false;for(let i=0;i<30;i++){const r=await cdp.send('Runtime.evaluate',{expression:'document.body?.textContent',returnByValue:true});if(r.result?.value==='isolated transport control'){documentReady=true;break;}await sleep(100);}
 assert(documentReady,'control starts from its actual minimal local document');
 await cdp.send('Runtime.evaluate',{expression:`window.__controller=new AbortController();window.__controlFetch=fetch(${JSON.stringify(origin+'/__wms652_paused_abort__')},{signal:window.__controller.signal}).then(r=>({success:true}),e=>({name:e.name,message:e.message,signalAborted:window.__controller.signal.aborted}))`,awaitPromise:false});
 report.observedPaused=await deadline(pausedPromise,5000,'actual paused GET');assert(report.observedPaused.networkId,'control needs actual networkId mapping');
 observe('control-stage',{stage:'explicit-client-abort-with-observed-request-paused',...paused});
 await cdp.send('Runtime.evaluate',{expression:'window.__controller.abort();true',returnByValue:true});
 const outcome=await cdp.send('Runtime.evaluate',{expression:'window.__controlFetch',returnByValue:true,awaitPromise:true});
 report.clientOutcome=outcome.result?.value;assert.equal(report.clientOutcome?.name,'AbortError');assert.equal(report.clientOutcome.signalAborted,true);
 const page=await cdp.send('Runtime.evaluate',{expression:'location.href',returnByValue:true});report.livePageAfterAbort=page.result.value;assert.equal(report.livePageAfterAbort,origin+'/__wms652_transport_document__');
 try{report.matchingLoadingFailed=await deadline(canceledPromise,5000,'matching loadingFailed after explicit abort');}catch(e){report.loadingFailedObservation=String(e);}
 try{report.staleFulfillResult=await cdp.send('Fetch.fulfillRequest',{requestId:paused.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/plain'}],body:Buffer.from('canceled-control-response').toString('base64')});}
 catch(e){report.staleFulfillError=errorDetails(e);}
 const bogus='__WMS652_never_observed_interception__';assert(bogus!==paused.requestId);
 try{report.unknownIdResult=await cdp.send('Fetch.fulfillRequest',{requestId:bogus,responseCode:200,body:''});}catch(e){report.unknownIdError=errorDetails(e);}
 assert.equal(report.unknownIdError?.code,-32602,'never-observed request ID must retain an actual error');assert.match(report.unknownIdError.message,/Invalid InterceptionId/);
 report.unknownIdIsUnexplained=true;
 report.status=report.staleFulfillError?.code===-32602&&/Invalid InterceptionId/.test(report.staleFulfillError.message)&&report.matchingLoadingFailed?.canceled===true?'MEASURED_EXPLICIT_ABORT_CANCELLATION_AND_UNEXPLAINED_UNKNOWN_ID':'INCONCLUSIVE';
 report.listenerErrors=errors;
}catch(e){report.failure=String(e);report.stack=e.stack;process.exitCode=1;}
finally{
 await writeFile(`${dir}/explicit-abort-probe.json`,JSON.stringify(report,null,2));
 await writeFile(`${dir}/explicit-abort-lifecycle.json`,JSON.stringify({lifecycle,lifecycleDropped},null,2));
 await writeFile(`${dir}/explicit-abort-chrome.log`,chromeLog);cdp?.ws.close();chrome.kill();console.log(JSON.stringify(report,null,2));
}
