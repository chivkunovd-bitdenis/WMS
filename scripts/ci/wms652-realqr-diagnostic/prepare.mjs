// Diagnostic copy only: frozen release runner remains byte-identical.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const file='frontend/tests-e2e/wms652-critical/browser.mjs';
const output='frontend/tests-e2e/wms652-critical/.lifecycle-diagnostic.untracked.mjs';
const source=await readFile(file,'utf8');
const actualMerge='ac845328b27b5be265962695e10766efddef339e';
assert.equal(source,execFileSync('git',['show',`${actualMerge}:${file}`],{encoding:'utf8'}));
const digest=text=>createHash('sha256').update(text).digest('hex');
const target='WMS652.realQrFlags[remount-after-lost-ack;supply_id=A]';
const telemetry=String.raw`
// Bounded metadata observation, no headers/bodies or altered protocol outcomes.
const lifecycle=[], commandMetadata=new Map(); let lifecycleDropped=0;
function observe(kind,data={}){try{const utc=Date.now(),mono=performance.now();if(lifecycle.length<20000)lifecycle.push({kind,nodeUtcMs:utc,nodeUtc:new Date(utc).toISOString(),nodeMonoMs:mono,nodeTimeOriginMs:performance.timeOrigin,...data});else lifecycleDropped++;}catch{lifecycleDropped++;}}
function fields(p={}){return {requestId:p.requestId,networkId:p.networkId,frameId:p.frameId,loaderId:p.loaderId,url:p.request?.url??p.frame?.url??p.url,requestMethod:p.request?.method,responseCode:p.responseCode,errorReason:p.errorReason,browserTimestamp:p.timestamp,browserWallTime:p.wallTime,canceled:p.canceled,errorText:p.errorText,blockedReason:p.blockedReason,type:p.type,contextId:p.executionContextId,uniqueContextId:p.executionContextUniqueId,frame:p.frame?{id:p.frame.id,parentId:p.frame.parentId,loaderId:p.frame.loaderId,url:p.frame.url}:undefined};}
const observedEvents=new Set(['Fetch.requestPaused','Network.requestWillBeSent','Network.loadingFailed','Network.loadingFinished','Page.frameNavigated','Page.frameDetached','Page.frameStartedLoading','Page.frameStoppedLoading','Runtime.executionContextDestroyed','Runtime.executionContextsCleared']);
`;
function replaceExactly(old,newValue){assert.equal(source.split(old).length,2,`original anchor ${old.slice(0,70)}`);assert.equal(copy.split(old).length,2);copy=copy.replace(old,newValue);}
let copy=source;
replaceExactly('class CDP {',telemetry+'\nclass CDP {');
replaceExactly('      const msg = JSON.parse(event.data);','      const msg = JSON.parse(event.data);\n      if(msg.id){const meta=commandMetadata.get(msg.id);observe(\'command-result\',{commandId:msg.id,...meta,error:msg.error,result:meta?.method===\'Browser.getVersion\'?msg.result:undefined});commandMetadata.delete(msg.id);}else if(observedEvents.has(msg.method))observe(\'protocol-event\',{method:msg.method,...fields(msg.params)});');
replaceExactly('Promise.resolve(f(msg.params)).catch(e => errors.push(String(e)))',"Promise.resolve(f(msg.params)).catch(e => {observe('listener-rejection',{method:msg.method,...fields(msg.params),error:String(e)});return errors.push(String(e));})");
replaceExactly('    await this.ready; const id = ++this.next;','    await this.ready; const id = ++this.next;\n    const metadata={method,...fields(params)};commandMetadata.set(id,metadata);observe(\'command-send\',{commandId:id,...metadata});');
replaceExactly("reject(Error(`CDP timeout ${method}`));","observe('command-timeout',{commandId:id,...commandMetadata.get(id)});reject(Error(`CDP timeout ${method}`));");
replaceExactly("  await cdp.send('Page.enable');await cdp.send('Runtime.enable');","  const environment=await cdp.send('Browser.getVersion');assert.equal(environment.product,'Chrome/141.0.7390.37');report.diagnosticEnvironment={node:process.version,platform:process.platform,arch:process.arch,...environment};\n  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');");
const invocationStart=copy.indexOf("  for(const [id,query,many] of [['supply_id=A'");
const invocationEnd=copy.indexOf("  assert(report.cases.every(one=>one.status==='PASS')",invocationStart);
assert(invocationStart>0&&invocationEnd>invocationStart);
copy=copy.slice(0,invocationStart)+'  await flagContracts();\n'+copy.slice(invocationEnd);
const entries="  const entries=[['supply_id=A','supply_id=wb-a',false],['supply_ids=A','supply_ids=wb-a',false],['supply_ids=A,B','supply_ids=wb-a,wb-b',true]];";
replaceExactly(entries,"  const entries=[['supply_id=A','supply_id=wb-a',false]];");
replaceExactly("  const variants=['alloff','qr','reprint','qr+reprint','pool','qr+pool','held-receipt','lost-accepted-ack','remount-after-lost-ack'];","  const variants=['remount-after-lost-ack'];");
replaceExactly("JSON.parse(readFileSync(new URL('./cases.json',import.meta.url),'utf8')),'complete exact browser IDs must execute'",`JSON.parse(readFileSync(new URL('./cases.json',import.meta.url),'utf8')).filter(id=>id===${JSON.stringify(target)}),'complete exact browser IDs must execute'`);
replaceExactly('  await writeFile(`${dir}/chrome.log`,chromeLog);',"  await writeFile(`${dir}/cdp-lifecycle.json`,JSON.stringify({lifecycle,lifecycleDropped,pendingCommands:[...commandMetadata]},null,2));\n  await writeFile(`${dir}/chrome.log`,chromeLog);");
function span(text,start,end){const a=text.indexOf(start),b=text.indexOf(end,a);assert(a>=0&&b>a);return text.slice(a,b);}
const protectedSpans={
 targetBody:span(source,'  for(const variant of variants)for(const [entry,query,many] of entries){','\nfunction resetGeometry'),
 routes:span(source,'async function intercept','async function scan'),
 fulfillment:span(source,'async function fulfill','function prepareState'),
 timing:span(source,'const sleep =','async function fulfill'),
 chromeLaunch:span(source,'const chromePath=','try {\n  let tabs'),
};
const anchors={targetBody:['  for(const variant of variants)for(const [entry,query,many] of entries){','\nfunction resetGeometry'],routes:['async function intercept','async function scan'],fulfillment:['async function fulfill','function prepareState'],timing:['const sleep =','async function fulfill'],chromeLaunch:['const chromePath=','try {\n  let tabs']};
for(const [name,[start,end]] of Object.entries(anchors))assert.equal(span(copy,start,end),protectedSpans[name],name+' byte preservation');
assert.equal(await readFile(file,'utf8'),source);
await writeFile(output,copy);
const transportObserverPath='frontend/tests-e2e/wms652-critical/.lifecycle-transport-observer.untracked.mjs';
const transportObserver='const errors=[];\n'+telemetry+'\n'+span(copy,'class CDP {','const sleep =')+'\nexport {CDP,observe,lifecycle,lifecycleDropped,errors};\n';
await writeFile(transportObserverPath,transportObserver);
const provenance={sourcePath:file,sourceSha256:digest(source),sourceActualTestedMerge:actualMerge,sourceBase:'7bbfafc68ef0834746e63f12a49db31a1977f030',transformedUntrackedPath:output,transformedSha256:digest(copy),selectedCase:target,transportObserverPath,transportObserverSha256:digest(transportObserver),protectedSpansSha256:Object.fromEntries(Object.entries(protectedSpans).map(([name,text])=>[name,digest(text)])),protectedSpansByteEqual:true,selection:'only invocation list, variant/entry lists and expected selected collection changed; entire target body preserved',telemetry:'command/result/listener metadata+Network observer domain; all rejects/errors/assertions unchanged',maxRecords:20000};
await writeFile(process.env.WMS652_DIAGNOSTIC_PROVENANCE||'docs/evidence/WMS-652/realqr-cdp-lifecycle-preparation-20261007/provenance.json',JSON.stringify(provenance,null,2)+'\n');
console.log(JSON.stringify(provenance,null,2));
