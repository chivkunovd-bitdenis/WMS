// WMS652 critical real-screen contracts. No mocked product controllers.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const bwip = require('bwip-js'), { PNG } = require('pngjs');
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, DataMatrixReader, QRCodeReader } = require('@zxing/library');
// Decode pixels handed to native print independently of the product renderer/claim.
// The canonical 60x80 fixture's matrix occupies the top 44%; text below must not
// confuse the detector. A swapped, truncated or different full CIS is a failure.
function decodedPngDataUrl(dataUrl){
  const png=PNG.sync.read(Buffer.from(dataUrl.split(',')[1],'base64'));
  const height=Math.floor(png.height*.44);
  for(const region of [{height},{height:png.height}]){
    const pixels=new Uint8ClampedArray(png.width*region.height);
    for(let i=0;i<pixels.length;i++)pixels[i]=(png.data[4*i]+2*png.data[4*i+1]+png.data[4*i+2])/4;
    const bitmap=new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,png.width,region.height)));
    for(const Reader of [DataMatrixReader,QRCodeReader]){try{return new Reader().decode(bitmap).getText()}catch{}}
  }
  throw Error('Native sink image contains no decodable full CIS QR/DataMatrix');
}
function decodedRenderedCodeDataUrl(dataUrl){
  const png=PNG.sync.read(Buffer.from(dataUrl.split(',')[1],'base64'));
  const pixels=new Uint8ClampedArray(png.width*png.height);
  for(let i=0;i<pixels.length;i++)pixels[i]=(png.data[4*i]+png.data[4*i+1]+png.data[4*i+2])/3;
  const bitmap=new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,png.width,png.height)));
  for(const Reader of [QRCodeReader,DataMatrixReader]){try{return new Reader().decode(bitmap).getText()}catch{}}
  throw Error('Rendered KIZ image is neither a decodable QR nor DataMatrix');
}
function decodedCis(job){return decodedPngDataUrl(job.imageDataUrl);}
const ORIGIN = process.env.WMS666_ORIGIN || 'http://127.0.0.1:16706';
const dir = process.env.WMS652_EVIDENCE;
const productSha = process.env.WMS666_PRODUCT_SHA;
if (!productSha) throw Error('Set WMS666_PRODUCT_SHA to the exact tested P SHA');
if (!dir) throw Error('Set WMS652_EVIDENCE to a persistent evidence directory');
await mkdir(dir,{recursive:true});
const qrCodes = ['*DUIkWJJF', '*DUIkNEXT'];
const qrImages = await Promise.all(qrCodes.map(text => bwip.toBuffer({bcid:'qrcode',text,scale:3})));
let requestLog=[],printLog=[],trace=[],blocked=[],errors=[],state,heldLookup,holdFirst;
let receiptMode='', heldPrint, acceptedPrints=new Map(), lostAck=false, boundOrders=new Map(), restored=false;
let cdp, mode='qr', selectionState, failedGroup, groupAttempts, addAttempts, createdRefs, heldAdd;
const report={sha:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),cases:[],physicalPaper:'NOT_TESTED',externalApi:'SYNTHETIC'};
class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.next = 0; this.pending = new Map(); this.listeners = new Map();
    // Ownership lives in this one CDP session. Never infer cancellation from an error string.
    this.generation = 0; this.paused = new Map(); this.network = new Map(); this.terminals = new WeakMap(); this.transport = [];
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = async event => {
      const msg = JSON.parse(event.data);
      if (msg.id) {
        const p = this.pending.get(msg.id); this.pending.delete(msg.id);
        if (p) {
          clearTimeout(p.timer);
          this.record({kind:'command-result',commandId:msg.id,method:p.method,...p.identity,nativeError:msg.error});
          if (msg.error) {
            if (p.retirableCandidate && msg.error.code === -32602 && msg.error.message === 'Invalid InterceptionId.'
              && await this.followedByOwnedFetchAbort(p)) {
              p.token.disposition = 'retired';
              const value = {retired:true,nativeError:msg.error,commandId:msg.id,method:p.method,...p.identity};
              this.record({kind:'retired-canceled-request',...value}); p.resolve(value);
            } else p.reject(Error(JSON.stringify(msg.error)));
          } else { if (p.token) p.token.disposition = 'completed'; p.resolve(msg.result); }
        }
      } else {
        this.observe(msg.method,msg.params);
        for (const f of this.listeners.get(msg.method) ?? []) Promise.resolve(f(msg.params)).catch(e => {
          errors.push(String(e));
          const request = msg.method === 'Fetch.requestPaused' ? this.paused.get(msg.params.requestId) : undefined;
          this.record({kind:'event-handler-error',eventMethod:msg.method,error:String(e),requestId:request?.requestId,
            networkId:request?.networkId,frameId:request?.frameId,generation:request?.generation,caseId:request?.caseId});
        });
      }
    };
  }
  currentCase() { return typeof report === 'undefined' ? null : report.currentCase ?? null; }
  record(value) { this.transport.push({utcMs:Date.now(),...value}); }
  async followedByOwnedFetchAbort(p) {
    const {token,identity,method} = p;
    if (method !== 'Fetch.fulfillRequest' || !token || token.ambiguous || token.attempts !== 1
      || token.generation !== identity.generation || token.caseId !== identity.caseId
      || !['paused','network-canceled'].includes(token.disposition)) return false;
    const terminal = this.terminals.get(token);
    if (!terminal) return false;
    if (!token.cancellation) await Promise.race([terminal.promise,sleep(300)]);
    return token.cancellation?.canceled === true
      && token.cancellation.errorText === 'net::ERR_ABORTED'
      && token.cancellation.type === 'Fetch'
      && ['paused','network-canceled'].includes(token.disposition)
      && token.caseId === identity.caseId
      && token.generation === identity.generation
      && !token.ambiguous;
  }
  observe(method, params) {
    if (method === 'Page.frameNavigated' || method === 'Runtime.executionContextsCleared') {
      this.generation++; this.record({kind:'generation-boundary',method,generation:this.generation,caseId:this.currentCase()});
    } else if (method === 'Fetch.requestPaused') {
      const token = {requestId:params.requestId,networkId:params.networkId,frameId:params.frameId,
        generation:this.generation,caseId:this.currentCase(),attempts:0,disposition:'paused'};
      let resolveTerminal;
      const promise = new Promise(resolve => { resolveTerminal = resolve; });
      this.terminals.set(token,{promise,resolve:resolveTerminal});
      // A reused Fetch token or ambiguous Network mapping cannot prove ownership.
      if (this.paused.has(token.requestId)) this.paused.get(token.requestId).ambiguous = true;
      else {
        this.paused.set(token.requestId,token);
        const owners = this.network.get(token.networkId) ?? new Set(); owners.add(token);
        this.network.set(token.networkId,owners);
        if (owners.size > 1) for (const owner of owners) owner.ambiguous = true;
      }
      this.record({kind:'request-paused',...token});
    } else if (method === 'Network.loadingFailed' || method === 'Network.loadingFinished') {
      for (const token of this.network.get(params.requestId) ?? []) {
        if (method === 'Network.loadingFinished') token.disposition = 'network-completed';
        else {
          token.cancellation = {canceled:params.canceled,errorText:params.errorText,type:params.type};
          token.disposition = params.canceled ? 'network-canceled' : 'network-failed';
        }
        this.terminals.get(token)?.resolve({method,params});
      }
      const owners = this.network.get(params.requestId) ?? new Set();
      this.record({kind:'network-terminal',method,networkId:params.requestId,
        generation:[...owners][0]?.generation ?? this.generation,caseId:[...owners][0]?.caseId ?? this.currentCase(),
        canceled:params.canceled,errorText:params.errorText,type:params.type});
    }
  }
  async send(method, params = {}) {
    await this.ready; const id = ++this.next;
    if (method === 'Page.navigate') this.generation++;
    const token = method.startsWith('Fetch.') && params.requestId ? this.paused.get(params.requestId) : undefined;
    const identity = {requestId:params.requestId,networkId:token?.networkId,frameId:token?.frameId,
      generation:this.generation,caseId:this.currentCase(),cancellation:token?.cancellation ? {...token.cancellation} : undefined};
    const retirableCandidate = method === 'Fetch.fulfillRequest' && token && !token.ambiguous && token.networkId && token.frameId
      && token.generation === identity.generation && token.caseId === identity.caseId && token.attempts === 0
      && ['paused','network-canceled'].includes(token.disposition);
    if (token) token.attempts++;
    this.record({kind:'command-send',commandId:id,method,...identity,attempt:token?.attempts});
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); this.record({kind:'command-timeout',commandId:id,method,...identity});
        reject(Error(`CDP timeout ${method}`));
      }, 12000);
      this.pending.set(id, {resolve,reject,timer,method,identity,token,retirableCandidate});
      this.ws.send(JSON.stringify({id,method,params}));
    });
  }
  on(method, callback) { this.listeners.set(method, [...this.listeners.get(method) ?? [], callback]); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function evaluate(expression) {
  const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
  return r.result.value;
}
async function until(expression, ms = 25000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await evaluate(`Boolean(${expression})`)) return; await sleep(150); }
  throw Error(`UI timeout: ${expression}`);
}
async function fulfill(id, body, status = 200, type = 'application/json') {
  const bytes = Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
  await cdp.send('Fetch.fulfillRequest', { requestId: id, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: type }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }], body: bytes.toString('base64') });
}
// Additional audit only. Unlike the old critical fixture, every product API
// below runs against the real local application and an isolated PostgreSQL DB.
const BACKEND=process.env.WMS666_BACKEND || 'http://127.0.0.1:16709';
let seed, held, heldStartWork, holdBareStartWork=false, failBareStartWork=false, pausePoint='', pausedOnce=false, failDeleteOnce=false, failTapeSupplyId='', failTapeOnce=false;
async function api(path,method='GET',body){
  const r=await fetch(BACKEND+'/proxy'+path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const text=await r.text(),data=text?JSON.parse(text):null;if(!r.ok)throw Error(JSON.stringify({path,status:r.status,data}));return data;
}
async function snapshot(){return (await fetch(BACKEND+'/snapshot')).json();}
async function printedHtmlCodes(){
  const sources=await evaluate(`(window.__AUDIT_HTML_PRINTS__||[]).map(html=>{
    const doc=new DOMParser().parseFromString(html,'text/html');
    return [...doc.querySelectorAll('[data-tape-block="cz"] img')].map(image=>image.src);
  })`);
  return sources.map(images=>images.map(decodedRenderedCodeDataUrl));
}
async function interceptLive({requestId,request}){
  const u=new URL(request.url),path=u.pathname.replace(/^\/api/,'');
  if(u.origin===ORIGIN&&!u.pathname.startsWith('/api/'))return cdp.send('Fetch.continueRequest',{requestId});
  if(u.origin===(process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17843')&&path==='/print'){
    const job=request.method==='POST'?JSON.parse(request.postData):null;
    if(job){
      const db=await snapshot(),decoded=decodedCis(job);
      printLog.push({captured_at:new Date().toISOString(),job,decoded,db,forwardedToActualHandler:true});
      trace.push({kind:'native-print-request-forwarded',key:job.idempotencyKey,decoded,handlerOrigin:u.origin});
    }
    return cdp.send('Fetch.continueRequest',{requestId});
  }
  if(u.origin!==ORIGIN){blocked.push(request.url);return cdp.send('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'});}
  const body=request.postData?JSON.parse(request.postData):null;
  if(failDeleteOnce&&request.method==='DELETE'&&path.includes(seed.order_ids[1])){failDeleteOnce=false;requestLog.push({method:'DELETE',path,status:503,syntheticFailure:true});return fulfill(requestId,{detail:{code:'wb_unavailable',message:'Synthetic WB refusal'}},503);}
  if(failTapeOnce&&request.method==='POST'&&path.endsWith('/order-print-tape')&&path.includes(failTapeSupplyId)){
    failTapeOnce=false;
    const response={detail:{code:'synthetic_print_refusal',message:'Synthetic one-time refusal for the second supply'}};
    requestLog.push({method:'POST',path,body,status:503,response,syntheticFailure:true});
    return fulfill(requestId,response,503);
  }
  if(failBareStartWork&&request.method==='POST'&&path.endsWith('/start-work')){
    failBareStartWork=false;
    const response={detail:{code:'synthetic_start_work_unavailable',message:'Synthetic one-time start-work refusal',retryable:true}};
    requestLog.push({method:'POST',path,body,status:503,response,syntheticFailure:true});
    trace.push({kind:'bare-start-work-failed-before-server-mutation',path});
    return fulfill(requestId,response,503);
  }
  async function forward(){
    const r=await fetch(BACKEND+'/proxy'+path+u.search,{method:request.method,headers:{'Content-Type':'application/json'},...(request.postData?{body:request.postData}:{})});
    const bytes=Buffer.from(await r.arrayBuffer());let response;
    try{response=JSON.parse(bytes.toString())}catch{response={binary:bytes.length}}
    requestLog.push({captured_at:new Date().toISOString(),method:request.method,path:path+u.search,body,status:r.status,response});
    return {bytes,status:r.status,type:r.headers.get('Content-Type')||'application/json'};
  }
  if(holdBareStartWork&&request.method==='POST'&&path.endsWith('/start-work')){
    holdBareStartWork=false;
    heldStartWork=async()=>{const r=await forward();await fulfill(requestId,r.bytes,r.status,r.type)};
    trace.push({kind:'bare-start-work-held-before-server-mutation',path});
    return;
  }
  if(path.endsWith('/print-claim')&&body?.target==='chz'&&!pausedOnce&&['before-claim','after-claim'].includes(pausePoint)){
    pausedOnce=true;
    if(pausePoint==='before-claim'){held=async()=>{const r=await forward();await fulfill(requestId,r.bytes,r.status,r.type)};return;}
    const r=await forward();held=()=>fulfill(requestId,r.bytes,r.status,r.type);return;
  }
  if(path.endsWith('/print-bindings/validate')&&pausePoint==='after-validation'&&!pausedOnce){
    pausedOnce=true;const r=await forward();held=()=>fulfill(requestId,r.bytes,r.status,r.type);return;
  }
  if(path.endsWith('/order-print-tape')&&pausePoint==='manual-response'&&!pausedOnce){
    pausedOnce=true;const r=await forward();held=()=>fulfill(requestId,r.bytes,r.status,r.type);return;
  }
  const r=await forward();return fulfill(requestId,r.bytes,r.status,r.type);
}
async function scanLive(code){
  await until(`document.querySelector('[data-packing-scan]')&&!document.querySelector('[data-packing-scan]').disabled`);
  await evaluate(`document.querySelector('[data-packing-scan]').focus()`);
  await cdp.send('Input.insertText',{text:code});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
}
const ownedChromeProfile=mkdtempSync(`${tmpdir()}/wms666-live-audit-`);
const chrome=spawn(process.env.CHROME_BIN||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',[
  '--headless=new','--mute-audio','--no-sandbox','--disable-gpu','--no-first-run',
  '--disable-background-networking',`--remote-debugging-port=${process.env.WMS666_CDP_PORT || '16707'}` ,
  `--user-data-dir=${ownedChromeProfile}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='';chrome.stderr.on('data',d=>chromeLog+=d);
try{
  let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch(`http://127.0.0.1:${process.env.WMS666_CDP_PORT || '16707'}/json/list`)).json();break}catch{await sleep(100)}}
  assert(tabs?.length,'isolated Chrome startup');cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  cdp.on('Fetch.requestPaused',interceptLive);cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',JSON.stringify({printQr:true,printChz:true,reprintChz:false,printChzCopies:2,reprintChzCopies:2}));localStorage.setItem('wms.print.labelSizeId','60x80');const q=new URLSearchParams(location.search),id=q.get('supply_id')||q.get('supply_ids');sessionStorage.setItem('wms:fbs:'+id+':stage','packing');sessionStorage.setItem('wms:fbs:assembly:'+id+':stage','packing');`});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__WMS_CAPTURE_PRINT_HTML__=true;window.__AUDIT_HTML_PRINTS__=[];window.open=()=>null;window.print=()=>{try{if(window.frameElement){window.frameElement.style.left='0';window.frameElement.style.top='0';window.frameElement.style.zIndex='2147483647';window.frameElement.style.background='white'}top.__AUDIT_HTML_PRINTS__.push(document.documentElement.outerHTML)}catch{}};`});
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  const variants=(process.env.WMS666_VARIANTS||'normal,delete-before-claim,delete-after-claim').split(',');
  for(const entry of (process.env.WMS666_ENTRIES||'supply_id,supply_ids').split(','))for(const variant of variants){
    await cdp.send('Page.navigate',{url:'about:blank'});await sleep(500);
    for(let i=0;i<100;i++){if((await(await fetch(BACKEND+'/idle')).json()).active===0)break;await sleep(100)}
    report.currentCase=variant==='bare-group-process'?(process.env.WMS666_STOP_AFTER_NATIVE_GROUP==='1'
      ?'WMS666.group.manual-tape-to-native-handler'
      :'WMS666.whole-process.bare-group-manual-before-scan')
      :variant==='bare-ordinary-process'?'WMS666.whole-process.bare-ordinary-manual-before-scan'
      :variant==='ozon-scope'?'WMS666.ozon-scope.actual-react-postgres'
      :variant.startsWith('unified-')?`WMS666.M41.${variant.slice('unified-'.length)}`
      :`WMS666.actualPool[${entry};${variant}]`;
    requestLog=[];printLog=[];trace=[];blocked=[];errors=[];held=null;heldStartWork=null;holdBareStartWork=false;failBareStartWork=variant==='bare-group-process'||variant==='bare-ordinary-process';pausedOnce=false;failTapeSupplyId='';failTapeOnce=false;
    pausePoint=/^(delete|replace)-/.test(variant)?(variant.endsWith('before-claim')?'before-claim':'after-claim'):'';
    if(variant==='manual-then-delete-scan')pausePoint='manual-response';
    if(variant.endsWith('-after-validation'))pausePoint='after-validation';
    if(variant==='rapid-scans'||variant==='multi-seller'||variant==='flags-after-claim')pausePoint='after-claim';
    const seedPath=variant==='ozon-scope'?'/seed-ozon':'/seed';
    const seedOptions=variant==='bare-group-process'
      ?{codes:4,multi:true,bare:true}
      :variant==='bare-ordinary-process'?{codes:4,multi:false,bare:true}
      :{codes:variant.startsWith('unified-')||variant==='ozon-scope'||variant==='clear-partial'||variant==='controls'||variant==='rapid-scans'||variant==='multi-seller'||variant.startsWith('manual-')?4:variant.startsWith('replace')?2:1,multi:variant==='multi-seller'||variant.startsWith('unified-'),stickers:qrImages.map(p=>p.toString('base64'))};
    if(process.env.WMS666_SEED_FILE){
      seed=JSON.parse(await readFile(process.env.WMS666_SEED_FILE,'utf8'));
      assert.equal(seed.supply_ids.length,2,'the supplied group seed has exactly two supplies');
    }else{
      seed=await(await fetch(BACKEND+seedPath,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(seedOptions)})).json();
    }
    try{
      if(variant==='clear-partial')await api(`/operations/fbs-supplies/${seed.supply_id}/order-print-tape`,'POST',{order_ids:seed.order_ids,layout_json:{units:[{block:'cz',copies:1}]},include_order_qr:false,reprint:false,allow_partial:false});
      const before=await snapshot();
      const wbRequestsBefore=await(await fetch('http://127.0.0.1:16710/requests')).json();
      await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs?${entry}=${seed.supply_ids.join(',')}`});
      await until(`document.querySelector('[data-order-id="${seed.order_ids[0]}"]')&&document.querySelector('[data-packing-scan]')`);
      if(variant==='bare-group-process'||variant==='bare-ordinary-process'){
        assert.equal(before.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id,null,'ordinary/group enters with no preseeded packaging task');
        const workspaceRequest=requestLog.find(row=>row.path.endsWith(`/operations/fbs-supplies/${seed.supply_id}/workspace`));
        assert(workspaceRequest?.response?.orders?.some(order=>order.product?.requires_honest_sign===true),
          'actual workspace API exposes Product.requires_honest_sign before task creation');
        assert.equal(await evaluate(`document.querySelectorAll('[data-order-id]').length`),2,'ordinary/group workspace contains two real orders');
        for(let i=0;i<150&&!requestLog.some(row=>row.path.endsWith('/start-work')&&row.status===503);i++)await sleep(100);
        const startWorkRefusal=requestLog.find(row=>row.path.endsWith('/start-work')&&row.status===503);
        assert(startWorkRefusal,'bare ordinary/group automatic prepare receives the one-time synthetic pre-mutation refusal');
        const afterPrepareRefusal=await snapshot();
        assert.equal(afterPrepareRefusal.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id,null,
          'failed automatic preparation does not create an accounting task');
        assert.deepEqual(afterPrepareRefusal.stock,before.stock,'failed automatic preparation does not move stock');
        const dialogs=[];
        // Manual KIZ for the bare order must remain available without a task.
        // The other mixed-group order is asserted by the frozen DOM/API contract.
        for(let index=0;index<1;index++){
          const orderId=seed.order_ids[index];
          const manualButton=`document.querySelector('[data-order-id="${orderId}"] [aria-label="Печать ЧЗ и ШК"]')`;
          assert(await evaluate(`!!${manualButton}`),'bare ordinary/group workspace exposes row manual KIZ action before first product scan');
          await evaluate(`${manualButton}.click()`);
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
          const dialog=await evaluate(`document.querySelector('[role="dialog"]')?.textContent||''`);
          assert.match(dialog,/ЧЗ|КИЗ|Киз/i,'manual print dialog offers the honest-sign block');
          dialogs.push(dialog);
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          await until(`window.__AUDIT_HTML_PRINTS__.length===${index+1}`);
          const renderedPng=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
          await writeFile(`${dir}/${entry}-bare-manual-${index+1}-render.png`,Buffer.from(renderedPng.data,'base64'));
          const renderedPdf=await cdp.send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true,transferMode:'ReturnAsBase64'});
          await writeFile(`${dir}/${entry}-bare-manual-${index+1}-render.pdf`,Buffer.from(renderedPdf.data,'base64'));
        }
        // The real manual-print component owns/closes its confirmation dialog
        // after dispatch; the workspace itself remains open around the alert.
        assert.equal(await evaluate(`!!document.querySelector('[data-testid="marking-print-confirm"]')`),false,
          'completed manual dispatch closes only its confirmation dialog');
        const tapes=requestLog.filter(row=>row.path.endsWith('/order-print-tape'));
        trace.push({kind:'completed-manual-print-confirmation-closed',supplyId:seed.supply_id,apiTapePath:tapes[0]?.path});
        assert.equal(tapes.length,1,'manual KIZ uses one real tape API request for the bare order before task creation');
        assert(tapes.every(row=>row.status===200),'manual KIZ reaches the actual tape API with no packaging task');
        const afterManual=await snapshot();
        assert.equal(afterManual.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id,null,'manual accounting does not require task creation');
        assert.equal(afterManual.markings.length,1,'manual printing binds one real pool CIS to the bare order');
        const decoded=await printedHtmlCodes();
        assert.equal(decoded.flat().length,2,'Chromium-rendered manual HTML contains both configured KIZ copies');
        assert(afterManual.markings.every(mark=>decoded.flat().filter(cis=>cis===mark.cis).length===2),
          'both rendered manual CIS copies belong to the persisted order binding');
        assert.deepEqual(new Set(afterManual.markings.map(mark=>mark.order_id)),new Set([seed.order_ids[0]]),
          'manual KIZ binding covers the bare order before product scan');
        const prepared=await snapshot();
        assert.equal(prepared.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id,null,
          'manual KIZ leaves the bare supply without an accounting task');
        await until(`[...document.querySelectorAll('[role="alert"]')].some(a=>[...a.querySelectorAll('button')].some(b=>/Повторить/.test(b.textContent)))`);
        const retryAlertText=await evaluate(`[...document.querySelectorAll('[role="alert"]')].find(a=>[...a.querySelectorAll('button')].some(b=>/Повторить/.test(b.textContent)))?.textContent.trim()`);
        assert(retryAlertText,'visible retry belongs to the alert produced by the failed automatic preparation');
        trace.push({kind:'explicit-prepare-retry',action:'Повторить',supplyId:seed.supply_id,startWorkFailure:startWorkRefusal.path,alertText:retryAlertText});
        await evaluate(`[...document.querySelectorAll('[role="alert"]')].flatMap(a=>[...a.querySelectorAll('button')]).find(b=>/Повторить/.test(b.textContent)).click()`);
        for(let i=0;i<150;i++){
          const current=await snapshot();
          if(current.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id)break;
          await sleep(100);
        }
        const autoPrepared=await snapshot();
        const automaticTaskId=autoPrepared.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id;
        assert(automaticTaskId,'explicit retry completes the existing automatic start-work action');
        assert.equal(requestLog.filter(row=>row.path.endsWith('/start-work')&&row.status===200).length,1,
          'one explicit retry creates the accounting task once');
        assert.equal(
          autoPrepared.supplies.filter(row=>row.packaging_task_id).length,
          before.supplies.filter(row=>row.packaging_task_id).length+1,
          'automatic retry creates exactly one accounting task for the bare supply',
        );
        assert.deepEqual(autoPrepared.stock,before.stock,'automatic task preparation does not move stock');
        for(let i=0;i<150&&(await(await fetch('http://127.0.0.1:16710/requests')).json()).length===wbRequestsBefore.length;i++)await sleep(100);
        const allWbRequests=await(await fetch('http://127.0.0.1:16710/requests')).json();
        const wbRequests=allWbRequests.slice(wbRequestsBefore.length);
        const stickerRequests=wbRequests.filter(row=>row.path==='/api/v3/orders/stickers');
        const expectedStickerRequests=variant==='bare-group-process'?2:1;
        assert.equal(stickerRequests.length,expectedStickerRequests,'each real supply makes one product API request to the local WB sticker endpoint');
        assert.deepEqual(new Set(stickerRequests.flatMap(row=>row.orderIds)),new Set(seed.order_ids.map((_,i)=>800392+i)),'local WB receives the actual seeded WB order identifiers for sticker preparation');
        assert(stickerRequests.every(row=>row.status===200),'the WB sticker endpoint accepts each exact preparation request');
        trace.push({kind:'wb-provider-request-accounting',stickerRequests,otherRealWbRequests:wbRequests.filter(row=>row.path!=='/api/v3/orders/stickers')});
        const withStickers=await snapshot();
        assert(withStickers.orders.filter(order=>seed.order_ids.includes(order.id)).every(order=>order.sticker_status==='ready'&&order.sticker_barcode),
          'returned local WB sticker numbers are persisted on both orders');
        assert(withStickers.print_assets.every(asset=>asset.kind!=='order_sticker'||(asset.status==='ready'&&asset.checksum)),
          'actual WB PNGs are persisted as ready print assets with checksums');
        // The second seeded order is task-backed in the mixed group and joins
        // the just-created task in an ordinary supply. Print its own KIZ through
        // the same real row action so the provider readback can prove both an
        // accepted and a rejected result without assigning the wrong row.
        const secondOrderId=seed.order_ids[1];
        const secondSupplyId=seed.supply_ids.length>1?seed.supply_ids[1]:seed.supply_id;
        const secondManualButton=`document.querySelector('[data-order-id="${secondOrderId}"] [aria-label="Печать ЧЗ и ШК"]')`;
        assert(await evaluate(`!!${secondManualButton}`),'task-backed second order exposes its row manual KIZ action');
        await evaluate(`${secondManualButton}.click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        for(let i=0;i<150&&!requestLog.some(row=>row.path.endsWith('/order-print-tape')&&row.path.includes(secondSupplyId)&&row.body?.order_ids?.includes(secondOrderId));i++)await sleep(100);
        const secondTape=requestLog.find(row=>row.path.endsWith('/order-print-tape')
          &&row.body?.order_ids?.includes(secondOrderId));
        assert(secondTape,'second order manual tape response was captured for the exact selected order');
        assert.equal(secondTape.status,200,'task-backed second order manual tape reaches the real API before provider outcome is configured');
        assert(!secondTape.response.order_errors?.length,'manual KIZ is printable before the synthetic WB rejection is introduced');
        await until(`window.__AUDIT_HTML_PRINTS__.length===2`);
        const secondManualPng=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(`${dir}/${entry}-bare-manual-after-task-render.png`,Buffer.from(secondManualPng.data,'base64'));
        const secondManualPdf=await cdp.send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true,transferMode:'ReturnAsBase64'});
        await writeFile(`${dir}/${entry}-bare-manual-after-task-render.pdf`,Buffer.from(secondManualPdf.data,'base64'));
        const afterTaskManual=await snapshot();
        assert.equal(afterTaskManual.markings.length,2,'each real order now owns one current manual KIZ');
        assert.equal(afterTaskManual.supplies.find(row=>row.id===seed.supply_id)?.packaging_task_id===null,false,
          'the explicit retry created the ordinary accounting task before the second order KIZ');
        trace.push({kind:'bare-group-manual-prepare-sticker-chain',before,workspaceRequest,startWorkRefusal,afterPrepareRefusal,dialogs,tapes,afterManual,prepared,autoPrepared,wbRequests,withStickers,decoded,afterTaskManual,chromiumPdfPaths:[`${entry}-bare-manual-1-render.pdf`,`${entry}-bare-manual-after-task-render.pdf`],chromiumPngPaths:[`${entry}-bare-manual-1-render.png`,`${entry}-bare-manual-after-task-render.png`]});
        const printJobsBeforeScan=printLog.length;
        const nativeBefore=await(await fetch('http://127.0.0.1:17843/_proof/status',{method:'POST'})).json();
        const claimsBefore=requestLog.filter(row=>row.path.endsWith('/scan-auto-print')).length;
        const physicalScans=[];
        for(let index=0;index<2;index++){
          await until(`document.querySelector('[data-packing-scan]')&&!document.querySelector('[data-packing-scan]').disabled`);
          const inputBefore=await evaluate(`({value:document.querySelector('[data-packing-scan]').value,disabled:document.querySelector('[data-packing-scan]').disabled})`);
          assert.equal(inputBefore.value,'',`physical group scan ${index+1} starts with a neutral scanner input`);
          const apiStart=requestLog.length;
          const printStart=printLog.length;
          const scanStartedAt=new Date().toISOString();
          await scanLive(seed.barcode);
          const target=Number(nativeBefore.accepted_png_count)+3*(index+1);
          for(let attempt=0;attempt<300;attempt++){
            const current=await(await fetch('http://127.0.0.1:17843/_proof/status',{method:'POST'})).json();
            if(current.accepted_png_count>=target)break;
            await sleep(100);
          }
          for(let attempt=0;attempt<100;attempt++){
            const idle=await(await fetch(`${BACKEND}/idle`)).json();
            const current=await snapshot();
            const packed=current.orders.find(row=>row.id===seed.order_ids[index])?.pack_status==='packed';
            if(idle.active===0&&packed)break;
            await sleep(100);
          }
          await sleep(700);
          const inputAfter=await evaluate(`({value:document.querySelector('[data-packing-scan]').value,disabled:document.querySelector('[data-packing-scan]').disabled})`);
          const settled=await snapshot();
          const idle=await(await fetch(`${BACKEND}/idle`)).json();
          const alerts=await evaluate(`[...document.querySelectorAll('[role="alert"]')].map(node=>node.textContent.trim()).filter(Boolean)`);
          physicalScans.push({index:index+1,barcode:seed.barcode,scanStartedAt,inputBefore,inputAfter,
            apiAttempts:requestLog.slice(apiStart).filter(row=>row.path.endsWith('/scan-auto-print')),
            nativeOutputs:printLog.slice(printStart),settledOrder:settled.orders.find(row=>row.id===seed.order_ids[index]),
            alerts,idle,settledAt:new Date().toISOString()});
          assert.equal(inputAfter.value,'',`physical group scan ${index+1} settles with a neutral scanner input`);
        }
        const scanPrints=printLog.slice(printJobsBeforeScan);
        const nativeAfter=await(await fetch('http://127.0.0.1:17843/_proof/status',{method:'POST'})).json();
        const scanClaims=requestLog.filter(row=>row.path.endsWith('/scan-auto-print'));
        const scanAttempts=scanClaims.slice(claimsBefore);
        const successfulClaims=scanAttempts.filter(row=>row.status===200);
        const exhaustedProbes=scanAttempts.filter(row=>row.status===409&&row.response?.detail?.code==='scan_product_exhausted');
        trace.push({kind:'native-group-input-boundaries',physicalScans});
        assert.equal(physicalScans.length,2,'two explicit physical barcode inputs were recorded independently');
        assert.equal(successfulClaims.length,2,'two physical scans claim one order from each supply');
        assert.deepEqual(successfulClaims.map(row=>row.response?.order_id),seed.order_ids,
          'the real scan queue selects the expected order in each seller/supply context');
        const expectedExhaustedProbes=variant==='bare-group-process'?1:0;
        assert.equal(exhaustedProbes.length,expectedExhaustedProbes,
          variant==='bare-group-process'
            ? 'the second physical scan probes the exhausted first supply before routing to the next supply'
            : 'the next order in the same supply needs no exhausted-supply probe');
        if(expectedExhaustedProbes){
          assert.equal(exhaustedProbes[0].response.detail.retryable,false,'the exhausted-supply probe is not a queued print intent');
        }
        assert.equal(physicalScans[0].apiAttempts.filter(row=>row.status===200).length,1,'the first physical input claims the first supply once');
        assert.equal(physicalScans[1].apiAttempts.filter(row=>row.status===200).length,1,'the second physical input claims the next supply once');
        assert.equal(physicalScans[1].apiAttempts.some(row=>row.status===409&&row.response?.detail?.code==='scan_product_exhausted'),
          expectedExhaustedProbes===1,
          'the second physical input records an exhausted first-supply probe only for grouped supplies');
        assert.equal(nativeAfter.accepted_png_count-nativeBefore.accepted_png_count,6,
          'the real Handler accepted one QR and two current-CIS copies for each scan intent');
        assert.equal(scanPrints.length,6,'all six browser requests were forwarded to the actual Handler');
        for(let index=0;index<2;index++){
          const claim=successfulClaims[index], orderId=claim.response.order_id;
          const order=afterTaskManual.orders.find(row=>row.id===orderId);
          const cis=afterTaskManual.markings.find(marking=>marking.order_id===orderId)?.cis;
          assert(order?.sticker_code&&cis,'each scanned seller order has its own persisted sticker and current CIS');
          const intentJobs=scanPrints.filter(row=>row.job.idempotencyKey===claim.response.scan_id
            ||row.job.idempotencyKey.startsWith(`${claim.response.scan_id}:`));
          assert.equal(intentJobs.length,3,'one scan intent emits exactly QR plus two CHZ copies');
          assert.equal(intentJobs.find(row=>row.job.idempotencyKey===claim.response.scan_id)?.decoded,order.sticker_barcode,
            'the native QR input decodes to the selected order exact persisted technical sticker barcode');
          const chz=intentJobs.filter(row=>row.job.idempotencyKey!==claim.response.scan_id);
          assert.equal(chz.length,2);
          assert(chz.every(row=>row.decoded===cis),'both native CHZ outputs decode to that order current full CIS');
          assert.equal(new Set(chz.map(row=>row.job.idempotencyKey)).size,2,'each CHZ copy has a unique copy key');
        }
        assert.equal(nativeAfter.product_sha,process.env.WMS666_PRODUCT_SHA);
        assert.equal(nativeAfter.runtime_checkout_sha,process.env.WMS666_PRODUCT_SHA);
        assert.equal(blocked.length,0,'only the explicit native Handler receives /print; unrelated external requests stay blocked');
        trace.push({kind:'group-native-handler-scan-results',nativeBefore,nativeAfter,physicalScans,scanAttempts,successfulClaims,exhaustedProbes,
          acceptedJobs:scanPrints.map(row=>({key:row.job.idempotencyKey,decoded:row.decoded}))});
        if(process.env.WMS666_STOP_AFTER_NATIVE_PREFIX==='1'){
          const afterNativePrefix=await snapshot();
          assert(afterNativePrefix.orders.filter(row=>seed.order_ids.includes(row.id)).every(row=>row.pack_status==='packed'),'both scanned orders are packed after native acceptance');
          assert.equal((await(await fetch(`${BACKEND}/idle`)).json()).active,0,'the native prefix settles all API writes');
          assert.equal(errors.length,0,'the native prefix has no browser or interception errors');
          assert.deepEqual(afterNativePrefix.stock,before.stock,'sticker preparation, manual KIZ, and scan packing do not move inventory stock');
          assert.deepEqual(new Set(afterNativePrefix.markings.map(row=>row.order_id)),new Set(seed.order_ids),
            'each scanned order retains exactly one current marking identity');
          trace.push({kind:'native-prefix-complete',orders:afterNativePrefix.orders.map(row=>({id:row.id,pack_status:row.pack_status})),
            markingIds:afterNativePrefix.markings.map(row=>({id:row.id,order_id:row.order_id,cis:row.cis})),stock:afterNativePrefix.stock,
            note:'Stopped before the separate WB-check and box workflows; all preceding API, manual-tape, scan, receipt, and binding assertions passed.'});
          const focused=Error('bounded native prefix complete');focused.focusedNativePrefix=true;throw focused;
        }
        const rejection=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:secondOrderId})}).then(r=>r.json());
        assert.equal(rejection.outcome,'rejected','provider rejection is configured only after both manual tape outputs exist');
        trace.push({kind:'synthetic-provider-rejection-configured-after-manual-print',rejection});
        await until(`document.querySelector('[data-testid="fbs-packing-check-wb"]')&&!document.querySelector('[data-testid="fbs-packing-check-wb"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-check-wb"]').click()`);
        const expectedSyncs=variant==='bare-group-process'?2:1;
        for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith('/markings/sync')).length<expectedSyncs;i++)await sleep(100);
        const wbChecks=requestLog.filter(row=>row.path.endsWith('/markings/sync'));
        assert.equal(wbChecks.length,expectedSyncs,'explicit UI action checks each selected supply with the synthetic WB boundary');
        assert(wbChecks.every(row=>row.status===200),'each synthetic WB readback request completes successfully');
        const postScan=await snapshot();
        assert(postScan.markings.length===2,'post-manual product scan keeps both order KIZ bindings current');
        assert.deepEqual(postScan.stock,before.stock,'manual/scan print operations do not move stock');
        const verifiedWorkspaces=await Promise.all((variant==='bare-group-process'?seed.supply_ids:[seed.supply_id]).map(id=>api(`/operations/fbs-supplies/${id}/workspace`)));
        const statuses=verifiedWorkspaces.flatMap(workspace=>workspace.orders.map(order=>({id:order.id,wb_order_id:order.wb_order_id,states:order.metadata.states.map(state=>state.status)})));
        const acceptedOrder=statuses.find(row=>row.id===seed.order_ids[0]);
        const rejectedOrder=statuses.find(row=>row.id===secondOrderId);
        assert(acceptedOrder?.states.includes('accepted'),'synthetic WB readback records accepted KIZ for the exact first order');
        assert(rejectedOrder?.states.includes('rejected'),'synthetic WB readback records rejected KIZ for the exact second order without erasing local output');
        const providerState=await fetch(BACKEND+'/provider-state').then(r=>r.json());
        const firstWbOrder=Number(acceptedOrder.wb_order_id),secondWbOrder=Number(rejectedOrder.wb_order_id);
        assert.equal(providerState.wb_sgtin_sent_values[firstWbOrder],postScan.markings.find(mark=>mark.order_id===seed.order_ids[0])?.cis,
          'the local WB test double received the first order exact full current CIS');
        assert.equal(providerState.wb_sgtin_sent_values[secondWbOrder],postScan.markings.find(mark=>mark.order_id===secondOrderId)?.cis,
          'the local WB test double received the second order exact full current CIS');
        assert(providerState.wb_sgtin_rejected_order_ids.includes(secondWbOrder),
          'the local WB test double independently recorded rejection for the second order');
        if(variant==='bare-group-process'&&process.env.WMS666_STOP_AFTER_NATIVE_GROUP==='1'){
          trace.push({kind:'group-native-focused-case-boundary',note:'Manual HTML tape, real React scans, final binding validation, exact Handler PNGs/receipts, provider readback, stock and order state were verified; separate cargo-box token flow is outside this native-print case.'});
        }else if(variant==='bare-group-process'){
          const beforeBox=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          const boxesTab=`[...document.querySelectorAll('[role="tab"]')].find(tab=>tab.textContent.trim()==='Короба')`;
          await until(`${boxesTab}&&!${boxesTab}.disabled`);
          await evaluate(`${boxesTab}.click()`);
          const boxPanel=`document.querySelector('[data-testid="fbs-assembly-boxes-panel-${seed.supply_id}"]')`;
          const createBox=`[...(${boxPanel})?.querySelectorAll('button')??[]].find(button=>button.textContent.trim()==='Добавить короба')`;
          await until(`${createBox}&&!${createBox}.disabled`);
          await evaluate(`${createBox}.click()`);
          for(let i=0;i<100;i++){const current=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);if(current.boxes.length)break;await sleep(100)}
          const afterBox=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          assert.equal(afterBox.boxes.length,beforeBox.boxes.length+1,'group packing can create a box after the same manual/scan workflow');
          const box=afterBox.boxes[0];
          const boxToggle=`document.querySelector('[data-testid="fbs-assembly-box-toggle-${box.id}"]')`;
          await until(`${boxToggle}?.textContent.trim()==='Закрыть короб'`);
          await evaluate(`${boxToggle}.click()`);
          await until(`${boxToggle}?.textContent.trim()==='Открыть короб'`);
          await evaluate(`${boxToggle}.click()`);
          await until(`${boxToggle}?.textContent.trim()==='Закрыть короб'`);
          const boxRow=`[...document.querySelectorAll('[data-testid="fbs-assembly-boxes-panel-${seed.supply_id}"] button')].find(button=>button.textContent.trim()==='Добавить товары')`;
          await until(`${boxRow}&&!${boxRow}.disabled`);
          await evaluate(`${boxRow}.click()`);
          await until(`document.querySelector('[role="dialog"]')?.textContent.includes('Добавить товары в короб')`);
          const quantityInput=`document.querySelector('[role="dialog"] input[type="number"]')`;
          await until(`${quantityInput}`);
          await evaluate(`(()=>{const input=${quantityInput};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,'1');input.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'1'}));input.dispatchEvent(new Event('change',{bubbles:true}));})()`);
          const assignButton=`[...document.querySelectorAll('[role="dialog"] button')].find(button=>button.textContent.trim()==='Добавить')`;
          await until(`${assignButton}&&!${assignButton}.disabled`);
          const assignmentRequestCount=requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/orders`)).length;
          await evaluate(`${assignButton}.click()`);
          for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/orders`)).length===assignmentRequestCount;i++)await sleep(100);
          const assignmentRequest=requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/orders`)).at(-1);
          assert.equal(assignmentRequest?.status,200,'the real UI assignment request adds the selected order to the box');
          const afterAssign=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          assert(afterAssign.boxes.find(row=>row.id===box.id)?.assigned_order_ids.includes(seed.order_ids[0]),'the exact selected order is persisted in the physical box');
          const qrButton=`[...document.querySelectorAll('[data-testid="fbs-assembly-boxes-panel-${seed.supply_id}"] button')].find(button=>button.textContent.trim()==='QR')`;
          await until(`${qrButton}&&!${qrButton}.disabled`);
          const retryQrCount=requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/retry-qr`)).length;
          await evaluate(`${qrButton}.click()`);
          for(let i=0;i<200&&requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/retry-qr`)).length===retryQrCount;i++)await sleep(100);
          const retryQrRequest=requestLog.filter(row=>row.path.endsWith(`/boxes/${box.id}/retry-qr`)).at(-1);
          assert.equal(retryQrRequest?.status,200,'the real UI requests the WB cargo-place QR after assignment');
          const afterQr=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          const qrBox=afterQr.boxes.find(row=>row.id===box.id);
          assert(qrBox?.wb_trbx_id,'the synthetic WB supplies the cargo-place identifier');
          assert.equal(qrBox?.qr_asset?.status,'ready','the returned WB sticker is persisted as a ready asset');
          const boxProviderState=await fetch(BACKEND+'/provider-state').then(r=>r.json());
          assert(boxProviderState.box_events.some(event=>event.operation==='GET_STICKER'&&event.supply_id===afterQr.supply.id&&event.trbx_ids.includes(qrBox.wb_trbx_id)),
            'the synthetic WB sticker endpoint received the exact persisted cargo-place identifier');
          await until(`document.querySelector('[role="dialog"]')?.textContent.includes('Проверка перед печатью')`);
          await until(`(()=>{const image=[...document.querySelectorAll('[role="dialog"] img')].find(item=>item.alt==='Печать QR короба WMS');return Boolean(image?.complete&&image.naturalWidth>0)})()`);
          const qrImageData=await evaluate(`(()=>{const image=[...document.querySelectorAll('[role="dialog"] img')].find(item=>item.alt==='Печать QR короба WMS');const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d').drawImage(image,0,0);return canvas.toDataURL('image/png')})()`);
          const decodedBoxQr=decodedPngDataUrl(qrImageData);
          assert.equal(decodedBoxQr,qrBox.wb_trbx_id,'the displayed QR decodes to the exact WB cargo-place ID');
          const qrPreviewPng=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
          await writeFile(`${dir}/group-box-qr-preview.png`,Buffer.from(qrPreviewPng.data,'base64'));
          const qrPreviewPdf=await cdp.send('Page.printToPDF',{printBackground:true,preferCSSPageSize:true,transferMode:'ReturnAsBase64'});
          await writeFile(`${dir}/group-box-qr-preview.pdf`,Buffer.from(qrPreviewPdf.data,'base64'));
          const closePreview=`[...document.querySelectorAll('[role="dialog"] button')].find(button=>button.textContent.trim()==='Закрыть')`;
          await evaluate(`${closePreview}.click()`);
          await until(`!document.querySelector('[role="dialog"]')?.textContent.includes('Проверка перед печатью')`);
          const afterBoxUi=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          assert(afterBoxUi.boxes.find(row=>row.id===box.id)?.assigned_order_ids.includes(seed.order_ids[0]),'closing QR preview preserves box assignment and current task state');
          assert.deepEqual(await snapshot().then(db=>db.stock),before.stock,'box creation, assignment, and QR retrieval leave inventory balance, reservations, and movements unchanged');
          trace.push({kind:'group-box-created-open-close-reopen-assigned-and-qr-fetched',beforeBox,afterBox,afterAssign,retryQrRequest,afterQr,decodedBoxQr,boxProviderState,afterBoxUi});
        }
        if(variant==='bare-ordinary-process'){
          await evaluate(`document.querySelector('[data-testid="fbs-packing-more-actions"]').click()`);
          await until(`[...document.querySelectorAll('[role="menuitem"]')].some(item=>item.textContent.includes('Всё упаковано'))`);
          const packAction=`[...document.querySelectorAll('[role="menuitem"]')].find(item=>item.textContent.includes('Всё упаковано'))`;
          assert.equal(await evaluate(`${packAction}.getAttribute('aria-disabled')==='true'`),false,
            'operator can explicitly request packing after task creation');
          await evaluate(`${packAction}.click()`);
          for(let i=0;i<150&&(await snapshot()).orders.some(order=>order.pack_status!=='packed');i++)await sleep(100);
          const packed=await snapshot();
          assert(packed.orders.every(order=>order.pack_status==='packed'),'explicit pack action completes ordinary orders');
          assert.deepEqual(packed.stock,before.stock,'explicit packing does not move inventory balance or create stock movements');
          trace.push({kind:'explicit-ordinary-pack-action',packed});
        }
        trace.push({kind:'bare-process-first-scan-after-manual',printLog,wbChecks,statuses,postScan,taskCounters:postScan.task_lines});
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant==='ozon-scope'){
        assert.equal(await evaluate(`document.querySelectorAll('[data-order-id]').length`),2,'two real Ozon postings load from PostgreSQL');
        const before=await snapshot();
        await evaluate(`document.querySelector('[data-order-id="${seed.order_ids[0]}"] input[type="checkbox"]').click()`);
        await until(`[...document.querySelectorAll('button')].some(b=>/^Печать выбранного \\(1\\)/.test(b.textContent))`);
        const label=await evaluate(`[...document.querySelectorAll('button')].find(b=>/^Печать выбранного \\(1\\)/.test(b.textContent))?.textContent`);
        trace.push({kind:'selected-ozon-action-label',label,selectedOrderId:seed.order_ids[0],allOrderIds:seed.order_ids});
        assert.match(label,/выбранного.*1/,'one selected Ozon posting is labelled as selected(1)');
        await evaluate(`[...document.querySelectorAll('button')].find(b=>/^Печать выбранного \\(1\\)/.test(b.textContent)).click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        for(let i=0;i<150&&!requestLog.some(r=>r.path.endsWith('/order-print-tape'));i++)await sleep(100);
        const tape=requestLog.find(r=>r.path.endsWith('/order-print-tape'));
        assert(tape,'actual Ozon manual print API request reached the real local server');
        assert.equal(tape.status,200,`actual Ozon tape response: ${JSON.stringify(tape.response)}`);
        assert.deepEqual(tape.body.order_ids,[seed.order_ids[0]],'selected print contains only the selected Ozon posting');
        for(let i=0;i<100&&await evaluate(`(window.__AUDIT_HTML_PRINTS__||[]).length===0`);i++)await sleep(100);
        const after=await snapshot();
        assert.equal(after.positions.length,4,'both Ozon postings retain their four actual positions');
        assert(after.orders.every(order=>order.marketplace==='ozon'),'the local product API returned Ozon records');
        assert.deepEqual(after.stock,before.stock,'label printing leaves stock, reserves, and movements unchanged');
        trace.push({kind:'selected-ozon-print-complete',tape,htmlCount:await evaluate(`(window.__AUDIT_HTML_PRINTS__||[]).length`),before,after});
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant.startsWith('unified-')){
        if(variant==='unified-partial-retry'){
          failTapeSupplyId=seed.supply_ids[1];failTapeOnce=true;
        }
        const bulk=await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]')!==null`);
        assert(bulk,'one shared selection/print panel is present for grouped supplies');
        assert.equal(await evaluate(`document.querySelectorAll('[data-packing-scan]').length`),1,'scanner remains available with manual controls');
        await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]').click()`);
        await until(`document.querySelectorAll('[data-order-id] input[type="checkbox"]:checked').length===2`);
        await evaluate(`[...document.querySelectorAll('button')].find(b=>/^Печать (выбранного|всего)/.test(b.textContent)).click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        await until(`window.__AUDIT_HTML_PRINTS__.length===1`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        if(variant==='unified-cancel'){
          await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find(b=>/Отмена|Закрыть/.test(b.textContent)).click()`);
          await sleep(300);
          assert.equal(requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length,1,'cancel stops remaining supply, does not replay successful one');
          assert.equal((await snapshot()).markings.length,1,'successful first supply stays committed');
        }else if(variant==='unified-partial-retry'){
          const firstCommitted=await snapshot();
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          for(let i=0;i<100&&!requestLog.some(r=>r.path.includes(seed.supply_ids[1])&&r.path.endsWith('/order-print-tape'));i++)await sleep(100);
          const partialTape=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
          assert.equal(partialTape.length,2,'coordinator stops after the second supply refusal');
          assert.equal(partialTape[0].status,200);assert.equal(partialTape[1].status,503);
          assert.deepEqual(partialTape[0].body.order_ids,[seed.order_ids[0]]);
          assert.deepEqual(partialTape[1].body.order_ids,[seed.order_ids[1]]);
          assert.equal(firstCommitted.markings.length,1,'first confirmed supply remains committed');
          assert.equal((await snapshot()).markings.length,1,'refused second supply has no binding');
          trace.push({kind:'coordinator-partial-stop',firstCommitted,afterRefusal:await snapshot(),partialTape});
          await until(`[...document.querySelectorAll('button')].some(b=>/Повторить/.test(b.textContent))`);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>/Повторить/.test(b.textContent)).click()`);
          for(let i=0;i<150&&requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length<3;i++)await sleep(100);
          const retriedTape=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
          assert.equal(retriedTape.length,3,'one explicit retry is sent for the refused supply');
          assert.equal(retriedTape[2].status,200);
          assert.deepEqual(retriedTape[2].body.order_ids,[seed.order_ids[1]],'retry never replays the successful first supply');
          const completed=await snapshot();
          assert.equal(completed.markings.length,2);
          await until(`window.__AUDIT_HTML_PRINTS__.length>=2`);
          const htmlCodes=await printedHtmlCodes();
          const decoded=htmlCodes.flat();
          assert.equal(decoded.length,2,'both manual coordinator outputs retain a decodable KIZ image');
          assert(decoded.every(cis=>completed.markings.filter(m=>m.cis===cis).length===1),
            'each decoded manual HTML payload maps to exactly one persisted code binding');
          assert.deepEqual(new Set(completed.markings.map(m=>m.order_id)),new Set(seed.order_ids),
            'the two actual supply orders each retain their own KIZ binding');
          trace.push({kind:'coordinator-retry-complete',retriedTape,completed,htmlCodes});
        }else if(variant==='unified-reload'){
          const htmlBeforeReload=await evaluate(`window.__AUDIT_HTML_PRINTS__[0]||''`);
          const decodedBeforeReload=(await printedHtmlCodes())[0]||[];
          const firstCommitted=await snapshot();
          assert.equal(firstCommitted.markings.length,1);
          await cdp.send('Page.reload');
          await until(`document.querySelectorAll('[data-order-id]').length===2&&document.querySelector('[data-packing-scan]')`);
          await sleep(500);
          const afterReload=await snapshot();
          assert.equal(requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length,1,'reload does not replay completed manual output');
          assert.deepEqual(afterReload.markings,firstCommitted.markings,'database success survives page reload');
          await evaluate(`document.querySelector('[data-order-id="${seed.order_ids[1]}"] input[type="checkbox"]').click()`);
          await until(`[...document.querySelectorAll('button')].some(b=>/^Печать выбранного \\(1\\)/.test(b.textContent))`);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>/^Печать выбранного \\(1\\)/.test(b.textContent)).click()`);
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          for(let i=0;i<150&&requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length<2;i++)await sleep(100);
          const tapes=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
          assert.equal(tapes.length,2);
          assert.deepEqual(tapes[0].body.order_ids,[seed.order_ids[0]]);
          assert.deepEqual(tapes[1].body.order_ids,[seed.order_ids[1]],'post-reload operator action addresses only the unfinished order');
          await until(`window.__AUDIT_HTML_PRINTS__.length>=1`);
          const completed=await snapshot();
          assert.equal(completed.markings.length,2);
          const decodedAfterReload=(await printedHtmlCodes())[0]||[];
          assert.equal(decodedBeforeReload.length,1,'first supply manual HTML contains one decodable KIZ');
          assert.equal(decodedAfterReload.length,1,'resumed supply manual HTML contains one decodable KIZ');
          assert(decodedBeforeReload.concat(decodedAfterReload).every(cis=>completed.markings.filter(m=>m.cis===cis).length===1),
            'both outputs still resolve to unique persisted bindings after reload');
          trace.push({kind:'coordinator-reload-resume',firstCommitted,afterReload,tapes,completed,htmlBeforeReload,decodedBeforeReload,decodedAfterReload});
        }else{
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          await until(`window.__AUDIT_HTML_PRINTS__.length===2`);
          const tapes=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
          assert.equal(tapes.length,2,'one successful manual batch per original supply');
          for(let i=0;i<2;i++)assert.deepEqual(tapes.find(r=>r.path.includes(seed.supply_ids[i])).body.order_ids,[seed.order_ids[i]],'seller/supply never receives neighbouring order IDs');
          assert.equal((await snapshot()).markings.length,2);
        }
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant==='clear-partial'){
        failDeleteOnce=true;
        await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]').click()`);
        await until(`document.querySelector('[data-testid="fbs-packing-clear-selected"]')&&!document.querySelector('[data-testid="fbs-packing-clear-selected"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-selected"]').click()`);
        await until(`document.querySelector('[data-testid="fbs-packing-clear-confirm"]')`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-confirm"]').click()`);
        await until(`document.body.textContent.includes('Очистка остановлена. Очищено: 1')`);
        const partial=await snapshot();trace.push({kind:'partial-clear',db:partial});
        assert.equal(partial.markings.length,1);assert.equal(partial.markings[0].order_id,seed.order_ids[1]);
        await until(`document.querySelector('[data-testid="fbs-packing-clear-selected"]')&&!document.querySelector('[data-testid="fbs-packing-clear-selected"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-selected"]').click()`);
        await until(`document.querySelector('[data-testid="fbs-packing-clear-confirm"]')`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-confirm"]').click()`);
        for(let i=0;i<100&&(await snapshot()).markings.length;i++)await sleep(100);
        assert.equal((await snapshot()).markings.length,0);
        assert.equal(requestLog.filter(r=>r.method==='DELETE'&&r.path.includes(seed.order_ids[0])).length,1,'successful first deletion not repeated');
        assert.equal(requestLog.filter(r=>r.method==='DELETE'&&r.path.includes(seed.order_ids[1])).length,2,'explicit retry only failed second order');
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant==='controls'){
        const inventory=await evaluate(`([...document.querySelectorAll('button,input')].map(e=>({tag:e.tagName,text:e.textContent,aria:e.getAttribute('aria-label'),testid:e.getAttribute('data-testid'),type:e.type,disabled:e.disabled})))`);
        trace.push({kind:'controls-inventory',inventory});
        const bulk=await evaluate(`!!document.querySelector('[data-testid="fbs-packing-select-all"]')`);
        if(entry==='supply_ids'){
          assert.equal(bulk,true,'proposed shared panel must expose selected/all actions in assembly too');
        }else{
          await evaluate(`document.querySelector('[data-order-id="${seed.order_ids[0]}"] input[type="checkbox"]').click()`);
          await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Печать выбранного (1)'))`);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Печать выбранного (1)')).click()`);
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')`);
          // Cancel preview: zero API mutation, then reopen selected scope.
          const before=requestLog.filter(r=>r.method!=='GET').length;
          await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find(b=>/Отмена|Закрыть/.test(b.textContent)).click()`);
          assert.equal(requestLog.filter(r=>r.method!=='GET').length,before);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Печать выбранного (1)')).click()`);
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          await until(`window.__AUDIT_HTML_PRINTS__.length>0`);
          const tape=requestLog.find(r=>r.path.endsWith('/order-print-tape'));
          assert.deepEqual(tape.body.order_ids,[seed.order_ids[0]],'selected scope');
          assert.equal((await snapshot()).markings.length,1,'one selection binds one unit');
          await until(`document.querySelector('[data-testid="fbs-packing-check-wb"]')&&!document.querySelector('[data-testid="fbs-packing-check-wb"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="fbs-packing-check-wb"]').click()`);
          for(let i=0;i<100&&!requestLog.some(r=>r.path.endsWith('/markings/sync'));i++)await sleep(100);
          const check=requestLog.find(r=>r.path.endsWith('/markings/sync'));
          assert(check&&check.path.includes(seed.supply_id)&&!check.body?.order_ids,'WB check uses entire supply despite selection');
          await until(`document.querySelector('[data-testid="fbs-packing-clear-selected"]')&&!document.querySelector('[data-testid="fbs-packing-clear-selected"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-selected"]').click()`);
          await until(`document.querySelector('[data-testid="fbs-packing-clear-preview"]')`);
          trace.push({kind:'clear-preview',text:await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-preview"]').textContent`)});
          await evaluate(`document.querySelector('[data-testid="fbs-packing-clear-confirm"]').click()`);
          for(let i=0;i<100&&(await snapshot()).markings.length;i++)await sleep(100);
          assert.equal((await snapshot()).markings.length,0,'selected code cleared');
          await until(`document.querySelector('[data-testid="fbs-packing-select-all"]')&&!document.querySelector('[data-testid="fbs-packing-select-all"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]').click()`);
          await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Печать выбранного (2)'))`);
          await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]').click()`);
          await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Печать всего (2)'))`);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Печать всего (2)')).click()`);
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          await until(`window.__AUDIT_HTML_PRINTS__.length===2`);
          const all=requestLog.filter(r=>r.path.endsWith('/order-print-tape')).at(-1);
          assert.deepEqual([...all.body.order_ids].sort(),[...seed.order_ids].sort(),'all scope');
          assert.equal((await snapshot()).markings.length,2);
          await until(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Всё упаковано'&&!b.disabled)`);
          await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Всё упаковано').click()`);
          for(let i=0;i<100&&(await snapshot()).orders.some(o=>o.pack_status!=='packed');i++)await sleep(100);
          assert((await snapshot()).orders.every(o=>o.pack_status==='packed'),'mass pack marks both units');
          trace.push({kind:'controls-success',db:await snapshot(),htmlCount:await evaluate(`window.__AUDIT_HTML_PRINTS__.length`)});
        }
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant==='rapid-scans'||variant==='multi-seller'||variant==='flags-after-claim'){
        await scanLive(seed.barcode);
        for(let i=0;i<100&&!held;i++)await sleep(100);assert(held);
        if(variant==='flags-after-claim'){
          await evaluate(`document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input').click()`);
        }else{
          await scanLive(seed.barcode);
        }
        await held();
        const count=variant==='flags-after-claim'?2:4;
        for(let i=0;i<150&&printLog.length<count;i++)await sleep(100);
        assert.equal(printLog.length,count,'snapshot copies survive queue/flag changes');
        const selections=requestLog.filter(r=>r.path.endsWith('/scan-auto-print')&&r.status===200);
        assert.equal(selections.length,variant==='flags-after-claim'?1:2);
        assert.equal(new Set(printLog.map(p=>p.decoded)).size,variant==='flags-after-claim'?1:2);
        assert(printLog.every(p=>p.db.markings.some(m=>m.cis===p.decoded)));
        if(variant==='flags-after-claim'){
          await scanLive(seed.barcode);await sleep(500);
          assert.equal(requestLog.filter(r=>r.path.endsWith('/scan-auto-print')&&r.status===200).length,1,'all-off next scan is inert');
        }
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else if(variant==='manual-then-delete-scan'||variant==='manual-after-validation'){
        const a=seed.order_ids[0];
        await api(`/operations/packaging-tasks/${seed.task_id}/lines/${seed.line_id}/pack`,'POST',{
          order_id:a,quantity:1,idempotency_key:'prepacked-manual-a'});
        await evaluate(`document.querySelector('[data-order-id="${a}"] [aria-label="Печать ЧЗ и ШК"]').click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        for(let i=0;i<100&&!held;i++)await sleep(100);assert(held,'manual tape response held after real DB binding');
        const manual=requestLog.find(r=>r.path.endsWith('/order-print-tape'))?.response;
        assert(manual?.orders?.[0]?.codes?.length===1,'real manual tape prepared canonical code');
        await api(`/operations/fbs-orders/${a}/kiz`,'DELETE');
        const next=await api(`/operations/fbs-supplies/${seed.supply_id}/scan-auto-print`,'POST',{
          barcode:seed.barcode,idempotency_key:'second-operator-scan',print_qr:false,print_chz:true,reprint_chz:false,await_honest_sign:true});
        assert.notEqual(next.order_id,a,'other physical unit selected');
        trace.push({kind:'manual-A-delete-scanner-B',manual,next,db:await snapshot()});
        await held();
        for(let i=0;i<50;i++){if(await evaluate(`window.__AUDIT_HTML_PRINTS__.length>0||document.querySelector('[role="alert"]')!==null`))break;await sleep(100)}
        const manualDispatched=await evaluate(`window.__AUDIT_HTML_PRINTS__.length>0`);
        const images=manualDispatched?await evaluate(`(()=>{const d=new DOMParser().parseFromString(window.__AUDIT_HTML_PRINTS__[0],'text/html');return [...d.querySelectorAll('[data-tape-block="cz"] img')].map(x=>x.src)})()`):[];
        const db=await snapshot(),decoded=images.map(url=>{
          const p=PNG.sync.read(Buffer.from(url.split(',')[1],'base64')),px=new Uint8ClampedArray(p.width*p.height);
          for(let i=0;i<px.length;i++)px[i]=(p.data[4*i]+2*p.data[4*i+1]+p.data[4*i+2])/4;
          return new DataMatrixReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(px,p.width,p.height)))).getText();
        });
        const html=await evaluate(`window.__AUDIT_HTML_PRINTS__[0]||''`);
        await writeFile(`${dir}/${entry}-manual-output.html`,html);
        trace.push({kind:'actual-html-dispatched',decoded,db});
        if(!manualDispatched)assert(await evaluate(`!!document.querySelector('[role="alert"]')?.textContent.trim()`),'stale manual attempt exposes a recoverable error');
        assert(decoded.every(cis=>db.markings.some(m=>m.order_id===a&&m.cis===cis)),
          'manual printed CIS must still belong to its original order after the other operator scan');
        report.cases.push({id:report.currentCase,status:'PASS'});
      }else{
      await scanLive(seed.barcode);
      if(pausePoint){
        for(let i=0;i<100&&!held;i++)await sleep(100);assert(held,'claim pause reached');
        const selection=requestLog.find(r=>r.path.endsWith('/scan-auto-print')&&r.status===200)?.response;
        assert(selection?.printed_codes?.length===1,'real backend issued pool CIS');
        const a=selection.order_id,b=seed.order_ids.find(id=>id!==a);
        if(variant.startsWith('replace')){
          const before=await snapshot(),next=before.codes.find(c=>c.status==='available');assert(next);
          const replacement=await api('/operations/fbs-orders/kiz/commit','POST',{
            pairs:[{order_id:a,value:next.cis,confirmed:true}],idempotency_key:'replace-pool-audit',scan_no_wb_wait:true});
          const db=await snapshot();assert(db.markings.some(m=>m.order_id===a&&m.cis===next.cis),'replacement saved');
          trace.push({kind:'operator-replace',oldOrder:a,replacement,db});
        }else{
          await api(`/operations/fbs-orders/${a}/kiz`,'DELETE');
          const manual=await api(`/operations/fbs-supplies/${seed.supply_id}/order-print-tape`,'POST',{
            order_ids:[b],layout_json:{units:[{block:'cz',copies:1}]},include_order_qr:false,reprint:false,allow_partial:false});
          trace.push({kind:'operator-delete-then-manual-other-order',oldOrder:a,newOrder:b,manual,db:await snapshot()});
        }
        await held();
      }
      for(let i=0;i<100&&printLog.length<2;i++)await sleep(100);
      if(!pausePoint)assert.equal(printLog.length,2,'two physical-emulator copies of one issued CIS');
      else if(printLog.length===0)assert(await evaluate(`!!document.querySelector('[role="alert"]')?.textContent.trim()`),'stale scan exposes a recoverable error');
      const selection=requestLog.find(r=>r.path.endsWith('/scan-auto-print')&&r.status===200).response;
      assert(printLog.every(p=>p.decoded===selection.printed_codes[0].cis_code),'real PNG matches pool response exactly');
      if(printLog.length)assert.equal(printLog[0].job.imageDataUrl,printLog[1].job.imageDataUrl,'copies identical');
      const aligned=printLog.every(p=>p.db.markings.some(m=>m.order_id===selection.order_id&&m.cis===p.decoded));
      assert.equal(aligned,true,'printed CIS must still belong to the scanned order at dispatch');
      report.cases.push({id:report.currentCase,status:'PASS'});
      }
    }catch(e){
      if(e?.focusedNativePrefix)report.cases.push({id:report.currentCase,status:'PASS'});
      else report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});
    }
    const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
    try {
      const html=await evaluate(`(window.__AUDIT_HTML_PRINTS__||[]).join('\\n<!-- WMS666 PRINT SPLIT -->\\n')`);
      if(html)await writeFile(`${dir}/${artifactName}.html`,html);
      const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
      await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
    } catch(e) { trace.push({kind:'browser-artifact-error',error:String(e)}); }
    console.log(JSON.stringify(report.cases.at(-1)));
    const redactPngDataUrls=value=>JSON.parse(JSON.stringify(value,(key,item)=>{
      if(key==='imageDataUrl'&&typeof item==='string'){
        const bytes=Buffer.from(item.split(',')[1]||'','base64');
        return {sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
      }
      return item;
    }));
    await writeFile(`${dir}/${artifactName}.json`,JSON.stringify(redactPngDataUrls({requestLog,printLog,trace,blocked,errors,finalDb:await snapshot()}),null,2));
  }
}finally{
  report.productSha=process.env.WMS666_PRODUCT_SHA || null;report.externalApi='SYNTHETIC_WB;REAL_LOCAL_API_POSTGRES_AND_NATIVE_HANDLER_EMULATED_PRINTER';
  try {
    await writeFile(`${dir}/result.json`,JSON.stringify(report,null,2));
    await writeFile(`${dir}/chrome.log`,chromeLog);
  } finally {
    cdp?.ws.close();chrome.kill();
    await new Promise(resolve=>{if(chrome.exitCode!==null)resolve();else chrome.once('exit',resolve)});
    rmSync(ownedChromeProfile,{recursive:true,force:true});
  }
}
process.exit(report.cases.some(c=>c.status==='FAIL')?1:0);
