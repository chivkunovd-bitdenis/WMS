// WMS652 critical real-screen contracts. No mocked product controllers.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(new URL('../../package.json', import.meta.url));
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
    this.generation = 0; this.paused = new Map(); this.network = new Map(); this.transport = [];
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.id) {
        const p = this.pending.get(msg.id); this.pending.delete(msg.id);
        if (p) {
          clearTimeout(p.timer);
          this.record({kind:'command-result',commandId:msg.id,method:p.method,...p.identity,nativeError:msg.error});
          if (msg.error) {
            if (p.retirable && !p.token.ambiguous && p.token.attempts === 1 && p.token.disposition === 'paused'
              && p.token.generation === this.generation && p.token.caseId === this.currentCase()
              && msg.error.code === -32602 && msg.error.message === 'Invalid InterceptionId.') {
              p.token.disposition = 'retired';
              const value = {retired:true,nativeError:msg.error,commandId:msg.id,method:p.method,...p.identity};
              this.record({kind:'retired-canceled-request',...value}); p.resolve(value);
            } else p.reject(Error(JSON.stringify(msg.error)));
          } else { if (p.token) p.token.disposition = 'completed'; p.resolve(msg.result); }
        }
      } else {
        this.observe(msg.method,msg.params);
        for (const f of this.listeners.get(msg.method) ?? []) Promise.resolve(f(msg.params)).catch(e => errors.push(String(e)));
      }
    };
  }
  currentCase() { return typeof report === 'undefined' ? null : report.currentCase ?? null; }
  record(value) { this.transport.push({utcMs:Date.now(),...value}); }
  observe(method, params) {
    if (method === 'Page.frameNavigated' || method === 'Runtime.executionContextsCleared') {
      this.generation++; this.record({kind:'generation-boundary',method,generation:this.generation,caseId:this.currentCase()});
    } else if (method === 'Fetch.requestPaused') {
      const token = {requestId:params.requestId,networkId:params.networkId,frameId:params.frameId,
        generation:this.generation,caseId:this.currentCase(),attempts:0,disposition:'paused'};
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
        if (token.generation !== this.generation || token.caseId !== this.currentCase()) continue;
        if (method === 'Network.loadingFinished') token.disposition = 'network-completed';
        else token.cancellation = {canceled:params.canceled,errorText:params.errorText,type:params.type};
      }
      this.record({kind:'network-terminal',method,networkId:params.requestId,generation:this.generation,caseId:this.currentCase(),canceled:params.canceled,errorText:params.errorText,type:params.type});
    }
  }
  async send(method, params = {}) {
    await this.ready; const id = ++this.next;
    if (method === 'Page.navigate') this.generation++;
    const token = method.startsWith('Fetch.') && params.requestId ? this.paused.get(params.requestId) : undefined;
    const identity = {requestId:params.requestId,networkId:token?.networkId,frameId:token?.frameId,
      generation:this.generation,caseId:this.currentCase(),cancellation:token?.cancellation ? {...token.cancellation} : undefined};
    const retirable = method === 'Fetch.fulfillRequest' && token && !token.ambiguous && token.networkId && token.frameId
      && token.generation === this.generation && token.caseId === identity.caseId && token.attempts === 0
      && token.disposition === 'paused' && token.cancellation?.canceled === true
      && token.cancellation.errorText === 'net::ERR_ABORTED' && token.cancellation.type === 'Fetch';
    if (token) token.attempts++;
    this.record({kind:'command-send',commandId:id,method,...identity,attempt:token?.attempts});
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); this.record({kind:'command-timeout',commandId:id,method,...identity});
        reject(Error(`CDP timeout ${method}`));
      }, 12000);
      this.pending.set(id, {resolve,reject,timer,method,identity,token,retirable});
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
  if(u.origin===(process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17845')&&path==='/print'){
    if(request.method==='OPTIONS')return fulfill(requestId,{});
    const job=JSON.parse(request.postData), db=await snapshot();
    const decoded=decodedCis(job),receipt='audit-'+(printLog.length+1);
    printLog.push({job,decoded,db,receipt,syntheticProviderOutcome:'accepted'});
    trace.push({kind:'synthetic-print-ack',key:job.idempotencyKey,decoded,receipt,outcome:'accepted'});
    return fulfill(requestId,{receipt});
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
    requestLog.push({method:request.method,path:path+u.search,body,status:r.status,response});
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
const chrome=spawn(process.env.CHROME_BIN||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',[
  '--headless=new','--mute-audio','--no-sandbox','--disable-gpu','--no-first-run',
  '--disable-background-networking','--disk-cache-size=16777216','--media-cache-size=16777216',
  `--remote-debugging-port=${process.env.WMS666_CDP_PORT || '16707'}` ,
  `--user-data-dir=${mkdtempSync(`${tmpdir()}/wms666-live-audit-`)}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='';chrome.stderr.on('data',d=>chromeLog+=d);
try{
  let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch(`http://127.0.0.1:${process.env.WMS666_CDP_PORT || '16707'}/json/list`)).json();break}catch{await sleep(100)}}
  assert(tabs?.length,'isolated Chrome startup');cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  cdp.on('Fetch.requestPaused',interceptLive);cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',JSON.stringify({printQr:false,printChz:true,reprintChz:false,printChzCopies:2,reprintChzCopies:2}));localStorage.setItem('wms.print.labelSizeId','60x80');const q=new URLSearchParams(location.search),id=q.get('supply_id')||q.get('supply_ids');sessionStorage.setItem('wms:fbs:'+id+':stage','packing');sessionStorage.setItem('wms:fbs:assembly:'+id+':stage','packing');`});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__WMS_CAPTURE_PRINT_HTML__=true;window.__AUDIT_HTML_PRINTS__=[];window.open=()=>null;window.print=()=>{try{if(window.frameElement){window.frameElement.style.left='0';window.frameElement.style.top='0';window.frameElement.style.zIndex='2147483647';window.frameElement.style.background='white'}top.__AUDIT_HTML_PRINTS__.push(document.documentElement.outerHTML)}catch{}};`});
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  const variants=(process.env.WMS666_VARIANTS||'normal,delete-before-claim,delete-after-claim').split(',');
  for(const entry of (process.env.WMS666_ENTRIES||'supply_id,supply_ids').split(','))for(const variant of variants){
    await cdp.send('Page.navigate',{url:'about:blank'});await sleep(500);
    for(let i=0;i<100;i++){if((await(await fetch(BACKEND+'/idle')).json()).active===0)break;await sleep(100)}
    report.currentCase=variant==='bare-group-process'?'WMS666.whole-process.bare-group-manual-before-scan'
      :variant==='bare-ordinary-process'?'WMS666.whole-process.bare-ordinary-manual-before-scan'
      :variant==='group-boxes-only'?'WMS666.group-boxes.create-assign-reopen-qr'
      :variant==='menu-skip'?'WMS666.named-supply.skip-honest-sign'
      :variant==='menu-transfer'?'WMS666.named-supply.selected-transfer'
      :variant==='unified-rejected-filter'?'WMS666.rejected-kiz-filter.actual-react-api'
      :variant==='ozon-scope'?'WMS666.ozon-scope.actual-react-postgres'
      :variant.startsWith('unified-')?`WMS666.M41.${variant.slice('unified-'.length)}`
      :`WMS666.actualPool[${entry};${variant}]`;
    requestLog=[];printLog=[];trace=[];blocked=[];errors=[];held=null;heldStartWork=null;holdBareStartWork=false;failBareStartWork=variant==='bare-group-process'||variant==='bare-ordinary-process';pausedOnce=false;failTapeSupplyId='';failTapeOnce=false;
    pausePoint=variant==='replace-ui-refusal-unlink'?'':(/^(delete|replace)-/.test(variant)?(variant.endsWith('before-claim')?'before-claim':'after-claim'):'');
    if(variant==='manual-then-delete-scan')pausePoint='manual-response';
    if(variant.endsWith('-after-validation'))pausePoint='after-validation';
    if(variant==='rapid-scans'||variant==='multi-seller'||variant==='flags-after-claim')pausePoint='after-claim';
    const seedPath=variant==='ozon-scope'?'/seed-ozon':'/seed';
    const seedOptions=variant==='bare-group-process'||variant==='group-boxes-only'
      ?{codes:4,multi:true,bare:true}
      :variant==='bare-ordinary-process'?{codes:4,multi:false,bare:true}
      :{codes:variant.startsWith('unified-')||variant==='ozon-scope'||variant==='clear-partial'||variant==='controls'||variant==='rapid-scans'||variant==='multi-seller'||variant.startsWith('manual-')||variant==='menu-transfer'?4:variant.startsWith('replace')?2:1,multi:variant==='multi-seller'||(variant.startsWith('unified-')&&variant!=='unified-rejected-filter'),transfer_target:variant==='menu-transfer',stickers:qrImages.map(p=>p.toString('base64'))};
    seed=await(await fetch(BACKEND+seedPath,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(seedOptions)})).json();
    const authorization=seed.headers?.Authorization??seed.headers?.authorization;
    assert.match(authorization||'',/^Bearer\s+\S+$/,'isolated API fixture returns the synthetic fulfillment session');
    const fulfillmentToken=authorization.replace(/^Bearer\s+/i,'');
    const tokenClaims=JSON.parse(Buffer.from(fulfillmentToken.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'),'base64').toString('utf8'));
    const printPreferencesKey=`wms:fbs:scan-auto-print:${tokenClaims.tenant_id||'unknown-tenant'}:${tokenClaims.sub||'unknown-user'}`;
    await cdp.send('Page.addScriptToEvaluateOnNewDocument',{
      source:`localStorage.setItem('wms_token_ff',${JSON.stringify(fulfillmentToken)});localStorage.setItem(${JSON.stringify(printPreferencesKey)},JSON.stringify({printQr:false,printChz:false,reprintChz:false}))`,
    });
    try{
      if(variant==='clear-partial')await api(`/operations/fbs-supplies/${seed.supply_id}/order-print-tape`,'POST',{order_ids:seed.order_ids,layout_json:{units:[{block:'cz',copies:1}]},include_order_qr:false,reprint:false,allow_partial:false});
      let uiReplaceFixture=null;
      if(variant==='replace-ui-refusal-unlink'){
        const orderId=seed.order_ids[0];
        const beforeBinding=await snapshot();
        const original=beforeBinding.codes.find(code=>code.status==='available');
        const replacementCode=beforeBinding.codes.find(code=>code.status==='available'&&code.id!==original?.id);
        assert(original&&replacementCode,'the row replacement fixture has two available pool CIS values');
        const initialValidation=await api('/operations/fbs-orders/kiz/validate','POST',{order_id:orderId,value:original.cis});
        assert.equal(initialValidation.ok,true,'the setup CIS validates through the real backend');
        const initialCommit=await api('/operations/fbs-orders/kiz/commit','POST',{
          pairs:[{order_id:orderId,value:original.cis,confirmed:true}],
          idempotency_key:'wms666-ui-row-original-bind',scan_no_wb_wait:false,
        });
        assert.equal(initialCommit[0]?.status,'ok','the setup CIS binds through the real backend/WB client');
        const setupDb=await snapshot();
        const bound=setupDb.markings.find(marking=>marking.order_id===orderId);
        assert.equal(bound?.cis,original.cis,'the original pool CIS is the exact current row binding');
        const wbOrder=Number((await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`)).orders.find(order=>order.id===orderId)?.wb_order_id);
        const rejection=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:orderId,cis_code:replacementCode.cis})}).then(r=>r.json());
        assert.equal(rejection.outcome,'rejected','only the proposed replacement CIS is refused by the loopback receiver');
        uiReplaceFixture={orderId,wbOrder,originalCis:original.cis,replacementCis:replacementCode.cis,initialValidation,initialCommit,rejection,setupDb};
      }
      const before=await snapshot();
      const wbRequestsBefore=await(await fetch('http://127.0.0.1:16710/requests')).json();
      await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs?${entry}=${seed.supply_ids.join(',')}`});
      if(variant==='replace-ui-refusal-unlink'){
        const {orderId,wbOrder,originalCis,replacementCis}=uiReplaceFixture;
        await until(`document.querySelector('[data-order-id="${orderId}"] [data-testid="fbs-kiz-row-input"]')&&document.querySelector('[data-order-id="${orderId}"] [data-testid="fbs-kiz-undo-inline"]')`);
        const rowInput=`document.querySelector('[data-order-id="${orderId}"] [data-testid="fbs-kiz-row-input"]')`;
        const focus=await evaluate(`(async()=>{const e=${rowInput};e.focus();await new Promise(resolve=>requestAnimationFrame(()=>resolve()));const active=document.activeElement;return {active:active?.matches('[data-testid="fbs-kiz-row-input"]')===true&&active.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderId)},activeOrderId:active?.closest('[data-order-id]')?.getAttribute('data-order-id'),activeTestId:active?.getAttribute('data-testid'),label:active?.getAttribute('aria-label'),value:active?.value}})()`);
        trace.push({kind:'row-kiz-input-focused-before-replacement',focus});
        assert.equal(focus.active,true,'keyboard input is focused in the exact current row after React settles');
        await cdp.send('Input.insertText',{text:replacementCis});
        await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
        await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
        for(let i=0;i<150&&!requestLog.some(row=>row.path.endsWith('/kiz/commit')&&row.body?.pairs?.some(pair=>pair.order_id===orderId&&pair.value===replacementCis));i++)await sleep(100);
        const replacementRequest=requestLog.find(row=>row.path.endsWith('/kiz/commit')&&row.body?.pairs?.some(pair=>pair.order_id===orderId&&pair.value===replacementCis));
        assert(replacementRequest,'the actual row replacement action reaches the KIZ commit API');
        assert(requestLog.some(row=>row.path.endsWith('/kiz/validate')&&row.body?.order_id===orderId&&row.body?.value===replacementCis),'the actual row replacement validates the selected CIS first');
        assert.equal(replacementRequest.body.scan_no_wb_wait,true,'the ordinary row replacement keeps WB verification asynchronous');
        assert.equal(await evaluate(`!![...document.querySelectorAll('[role="dialog"]')].find(d=>d.getClientRects().length>0&&d.querySelector('[data-testid="fbs-kiz-confirm-replace"]'))`),false,'ordinary row replacement does not invent a confirmation dialog');
        assert.equal(requestLog.filter(row=>row.path.endsWith('/scan-auto-print')).length,0,'this manual row path did not first issue an unrelated product-barcode selection');
        const pollResponse=await fetch(BACKEND+'/run-pending-kiz-poll',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({supply_id:seed.supply_id})});
        assert.equal(pollResponse.status,200,'the local fixture advances the real seller-level pending-KIZ poll after the asynchronous UI commit');
        const pendingPoll=await pollResponse.json();
        assert(pendingPoll.provider_state.wb_http_receiver.requests.some(row=>row.orderId===wbOrder&&row.method==='PUT'&&row.status===409&&row.body?.sgtins?.[0]===replacementCis),'the real poll sends the proposed CIS through the WB client and the loopback receiver refuses that exact value');
        const polledMarking=pendingPoll.local_state.markings.find(marking=>marking.order_id===orderId);
        trace.push({kind:'real-seller-pending-kiz-poll-advanced-by-local-fixture',pendingPoll,polledMarking});
        assert.equal(polledMarking?.cis,replacementCis,'the scheduler reconciles the exact proposed row binding');
        assert.equal(polledMarking?.status,'rejected','the scheduler persists the exact WB refusal before the operator refreshes the workspace');
        const verifyButton='document.querySelector(\'[data-testid="fbs-packing-check-wb"]\')';
        await until(`${verifyButton}&&!${verifyButton}.disabled`);
        const syncBefore=requestLog.filter(row=>row.path.endsWith('/markings/sync')).length;
        await evaluate(`${verifyButton}.click()`);
        for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith('/markings/sync')).length===syncBefore;i++)await sleep(100);
        assert.equal(requestLog.filter(row=>row.path.endsWith('/markings/sync')).length,syncBefore+1,'the visible Проверить в WB control refreshes the asynchronously recorded verdict');
        let afterRefusal,receiverAfterRefusal;
        for(let i=0;i<150;i++){
          [afterRefusal,receiverAfterRefusal]=await Promise.all([snapshot(),fetch(BACKEND+'/provider-state').then(r=>r.json())]);
          const rejectedPut=receiverAfterRefusal.wb_http_receiver.requests.some(row=>row.orderId===wbOrder&&row.method==='PUT'&&row.status===409&&row.body?.sgtins?.[0]===replacementCis);
          const current=afterRefusal.markings.find(marking=>marking.order_id===orderId);
          if(rejectedPut&&current?.cis===replacementCis&&current.status==='rejected')break;
          await sleep(100);
        }
        const currentAfterRefusal=afterRefusal.markings.find(marking=>marking.order_id===orderId);
        assert.equal(currentAfterRefusal?.cis,replacementCis,'asynchronous WB refusal leaves the exact proposed CIS bound locally');
        assert.equal(currentAfterRefusal?.status,'rejected','the local current binding records the WB refusal');
        assert(receiverAfterRefusal.wb_http_receiver.requests.some(row=>row.orderId===wbOrder&&row.method==='PUT'&&row.status===409&&row.body?.sgtins?.[0]===replacementCis),'the real WB client sent the exact replacement CIS and received the configured refusal');
        await until(`document.querySelector('[data-order-id="${orderId}"]')?.textContent.includes('WB не принял ЧЗ')`);
        const undo=`document.querySelector('[data-order-id="${orderId}"] [data-testid="fbs-kiz-undo-inline"]')`;
        await until(`${undo}&&!${undo}.disabled`);
        await evaluate(`${undo}.click()`);
        const undoDialog=`[...document.querySelectorAll('[role="dialog"]')].find(d=>d.getClientRects().length>0&&[...d.querySelectorAll('button')].some(b=>b.textContent.trim()==='Отменить КИЗ'))`;
        await until(`${undoDialog}`);
        const undoText=await evaluate(`${undoDialog}.textContent`);
        assert.match(undoText,/Привязка снимется у нас и в WB/,'the unlink dialog explains its WMS/WB effect');
        await evaluate(`[...${undoDialog}.querySelectorAll('button')].find(b=>b.textContent.trim()==='Отменить КИЗ').click()`);
        for(let i=0;i<150&&!requestLog.some(row=>row.method==='DELETE'&&row.path.endsWith(`/operations/fbs-orders/${orderId}/kiz`));i++)await sleep(100);
        const unlinkRequest=requestLog.find(row=>row.method==='DELETE'&&row.path.endsWith(`/operations/fbs-orders/${orderId}/kiz`));
        assert.equal(unlinkRequest?.status,204,'row unlink action reaches the real local API');
        const afterUnlink=await snapshot();
        assert.equal(afterUnlink.markings.some(marking=>marking.order_id===orderId),false,'the selected current WMS binding is removed');
        assert.equal(afterUnlink.codes.find(code=>code.cis===originalCis)?.status,'void','replacement retired the old CIS and unlink does not revive that history');
        assert.equal(afterUnlink.codes.find(code=>code.cis===replacementCis)?.status,'available','unlink returns the currently rejected CIS to the scoped pool');
        const receiverAfterUnlink=await(await fetch(BACKEND+'/provider-state')).json();
        assert.equal(receiverAfterUnlink.wb_http_receiver.sgtinByOrder[wbOrder],undefined,'independent WB receiver state has no SGTIN after unlink');
        const finalWrites=receiverAfterUnlink.wb_http_receiver.requests.filter(row=>row.orderId===wbOrder&&['PUT','DELETE'].includes(row.method));
        assert.deepEqual(finalWrites.slice(-1).map(row=>[row.method,row.status]),[['DELETE',204]],'the actual UI unlink sends one provider DELETE for the rejected current binding');
        const neighborAfter=afterUnlink.markings.filter(marking=>marking.order_id!==orderId);
        assert.deepEqual(neighborAfter,before.markings.filter(marking=>marking.order_id!==orderId),'the neighbor order binding remains unchanged through replacement refusal and unlink');
        assert.deepEqual(afterUnlink.stock,before.stock,'replacement refusal and unlink leave physical stock/reservations unchanged');
        trace.push({kind:'actual-row-replacement-wb-refusal-keeps-current-then-row-unlink',fixture:uiReplaceFixture,focus,replacementRequest,afterRefusal,receiverAfterRefusal,unlinkRequest,undoText,afterUnlink,receiverAfterUnlink});
        report.cases.push({id:report.currentCase,status:'PASS'});
        const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
        await writeFile(`${dir}/${artifactName}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,finalDb:afterUnlink},null,2));
        const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
        console.log(JSON.stringify(report.cases.at(-1)));
        continue;
      }
      if(variant==='group-boxes-only'){
        const firstSupplyId=seed.supply_ids[0],firstOrderId=seed.order_ids[0];
        await until(`document.body.textContent.includes('Сборка · 2 поставки')&&[...document.querySelectorAll('[role="tab"]')].some(t=>t.textContent.trim()==='Короба')`);
        await evaluate(`[...document.querySelectorAll('[role="tab"]')].find(t=>t.textContent.trim()==='Короба').click()`);
        const panel=`document.querySelector('[data-testid="fbs-assembly-boxes-panel-${firstSupplyId}"]')`;
        const create=`[...(${panel})?.querySelectorAll('button')??[]].find(b=>b.textContent.trim()==='Добавить короба')`;
        await until(`${panel}&&${create}&&!${create}.disabled`);
        const beforeWorkspace=await api(`/operations/fbs-supplies/${firstSupplyId}/workspace`);
        await evaluate(`${create}.click()`);
        for(let i=0;i<120&&!requestLog.some(r=>r.method==='POST'&&r.path.includes(`/operations/fbs-supplies/${firstSupplyId}/boxes`));i++)await sleep(100);
        const createRequest=requestLog.findLast(r=>r.method==='POST'&&r.path.includes(`/operations/fbs-supplies/${firstSupplyId}/boxes`));
        const afterCreate=await api(`/operations/fbs-supplies/${firstSupplyId}/workspace`);
        assert.equal(createRequest?.status,201,`group box create API succeeds: ${JSON.stringify(createRequest)}`);
        assert.equal(afterCreate.boxes.length,beforeWorkspace.boxes.length+1,'group boxes panel creates exactly one persisted box');
        const box=afterCreate.boxes.at(-1);
        const toggle=`document.querySelector('[data-testid="fbs-assembly-box-toggle-${box.id}"]')`;
        await until(`${toggle}?.textContent.trim()==='Закрыть короб'`);
        await evaluate(`${toggle}.click()`);
        await until(`${toggle}?.textContent.trim()==='Открыть короб'`);
        await evaluate(`${toggle}.click()`);
        await until(`${toggle}?.textContent.trim()==='Закрыть короб'`);
        const addItems=`[...(${panel})?.querySelectorAll('button')??[]].find(b=>b.textContent.trim()==='Добавить товары')`;
        await until(`${addItems}&&!${addItems}.disabled`);
        await evaluate(`${addItems}.click()`);
        const assignDialog=`[...document.querySelectorAll('[role="dialog"]')].find(d=>d.getClientRects().length>0&&d.textContent.includes('Добавить товары в короб'))`;
        await until(`${assignDialog}`);
        const qty=`(${assignDialog})?.querySelector('input[type="number"]')`;
        await until(`${qty}`);
        await evaluate(`${qty}.focus()`);
        const focusedQuantity=await evaluate(`(()=>{const dialog=${assignDialog};const input=${qty};return {dialogVisible:!!dialog,active:document.activeElement===input}})()`);
        assert(focusedQuantity.dialogVisible&&focusedQuantity.active,'the actual visible group assignment quantity field receives keyboard focus');
        await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'1',code:'Digit1',text:'1',unmodifiedText:'1',windowsVirtualKeyCode:49});
        await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'1',code:'Digit1',windowsVirtualKeyCode:49});
        const quantityInputState=await evaluate(`(()=>{const dialog=${assignDialog};const input=${qty};return {dialogVisible:!!dialog,value:input?.value,active:document.activeElement===input,disabled:input?.disabled,addDisabled:[...dialog?.querySelectorAll('button')??[]].find(b=>b.textContent.trim()==='Добавить')?.disabled}})()`);
        trace.push({kind:'group-box-quantity-input',quantityInputState});
        assert.equal(quantityInputState.value,'1','real keyboard input updates the selected box quantity');
        const assign=`[...(${assignDialog})?.querySelectorAll('button')??[]].find(b=>b.textContent.trim()==='Добавить')`;
        await until(`${assign}&&!${assign}.disabled`);
        await evaluate(`${assign}.click()`);
        for(let i=0;i<120&&!requestLog.some(r=>r.path.endsWith(`/boxes/${box.id}/orders`));i++)await sleep(100);
        const assignment=requestLog.findLast(r=>r.path.endsWith(`/boxes/${box.id}/orders`));
        assert.equal(assignment?.status,200,`group box assignment API succeeds: ${JSON.stringify(assignment)}`);
        const assigned=await api(`/operations/fbs-supplies/${firstSupplyId}/workspace`);
        assert(assigned.boxes.some(row=>row.id===box.id&&row.assigned_order_ids.includes(firstOrderId)),'the selected order is assigned to the exact persisted group box');
        const qr=`[...(${panel})?.querySelectorAll('button')??[]].find(b=>b.textContent.trim()==='QR')`;
        await until(`${qr}&&!${qr}.disabled`);
        await evaluate(`${qr}.click()`);
        for(let i=0;i<120;i++){
          const current=await api(`/operations/fbs-supplies/${firstSupplyId}/workspace`);
          const updated=current.boxes.find(row=>row.id===box.id);
          if(updated?.qr_asset?.status==='ready'&&updated.qr_asset.preview_url)break;
          await sleep(100);
        }
        const withQr=await api(`/operations/fbs-supplies/${firstSupplyId}/workspace`);
        const qrBox=withQr.boxes.find(row=>row.id===box.id);
        assert(qrBox?.qr_asset?.status==='ready'&&qrBox.qr_asset.preview_url,'the group box obtains its provider QR after explicit operator request');
        const providerState=await fetch(BACKEND+'/provider-state').then(r=>r.json());
        assert(providerState.box_events.length>0,'the synthetic WB box provider records the QR request independently');
        const after=await snapshot();
        assert.deepEqual(after.stock,before.stock,'box creation and assignment do not move physical stock');
        trace.push({kind:'group-boxes-only',firstSupplyId,firstOrderId,beforeWorkspace,createRequest,afterCreate,assignment,assigned,withQr,providerState,stockBefore:before.stock,stockAfter:after.stock});
        report.cases.push({id:report.currentCase,status:'PASS'});
        const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
        const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
        await writeFile(`${dir}/${artifactName}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,finalDb:after},null,2));
        console.log(JSON.stringify(report.cases.at(-1)));
        continue;
      }
      if(variant==='menu-skip'){
        await until(`document.querySelector('[data-testid="fbs-packing-actions"]')&&document.querySelector('[data-order-id="${seed.order_ids[0]}"]')`);
        const before=await snapshot();
        const beforeWorkspace=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-more-actions"]').click()`);
        await until(`document.querySelector('[role="menu"]')&&document.querySelector('[data-testid="fbs-skip-honest-sign"]')`);
        const menuState=await evaluate(`(()=>{const item=document.querySelector('[data-testid="fbs-skip-honest-sign"]');return {text:item?.textContent.trim(),disabled:item?.classList.contains('Mui-disabled')}})()`);
        assert.equal(menuState.disabled,false,'named-supply skip action is available in the supply menu');
        await evaluate(`document.querySelector('[data-testid="fbs-skip-honest-sign"]').click()`);
        await until(`document.querySelector('[data-testid="fbs-skip-honest-sign-confirm"]')`);
        const confirmation=await evaluate(`([...document.querySelectorAll('[role="dialog"]')].find(dialog=>dialog.getClientRects().length>0&&dialog.querySelector('[data-testid="fbs-skip-honest-sign-confirm"]'))?.textContent)||''`);
        assert.match(confirmation,/со всей поставки/,'operator sees that skip applies to this whole supply before confirming');
        await evaluate(`document.querySelector('[data-testid="fbs-skip-honest-sign-confirm"]').click()`);
        for(let i=0;i<120&&!requestLog.some(row=>row.path.endsWith('/honest-sign-skip'));i++)await sleep(100);
        const skipRequest=requestLog.find(row=>row.path.endsWith('/honest-sign-skip'));
        assert.equal(skipRequest?.status,200,`the named supply skip action succeeds: ${JSON.stringify(skipRequest)}`);
        const after=await snapshot();
        const afterWorkspace=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
        assert.equal(afterWorkspace.supply.honest_sign_skipped,true,'the selected supply records the explicit skip');
        assert.equal(afterWorkspace.supply.id,beforeWorkspace.supply.id);
        assert.deepEqual(after.codes,before.codes,'skip changes the supply requirement, not pool code ownership');
        assert.deepEqual(after.stock,before.stock,'skip does not move physical stock, reservations, or movements');
        trace.push({kind:'named-supply-skip-confirmed',menuState,confirmation,skipRequest,before,beforeWorkspace,after,afterWorkspace});
        report.cases.push({id:report.currentCase,status:'PASS'});
        const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
        const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
        await writeFile(`${dir}/${artifactName}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,finalDb:after},null,2));
        console.log(JSON.stringify(report.cases.at(-1)));
        continue;
      }
      if(variant==='menu-transfer'){
        const orderId=seed.order_ids[0],targetId=seed.transfer_target_id;
        assert(targetId,'fixture supplies one same-seller transfer target');
        await until(`document.querySelector('[data-testid="fbs-packing-actions"]')&&document.querySelector('[data-order-id="${orderId}"]')`);
        const before=await snapshot();
        const sourceBefore=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
        const targetBefore=await api(`/operations/fbs-supplies/${targetId}/workspace`);
        const sourceOrder=sourceBefore.orders.find(order=>order.id===orderId);
        assert(sourceOrder,'selected order belongs to the source supply before transfer');
        const rowCheckbox=`document.querySelector('[data-order-id="${orderId}"] input[type="checkbox"]')`;
        await evaluate(`${rowCheckbox}.click()`);
        await until(`document.querySelector('[data-testid="fbs-packing-actions"]')`);
        const manualButton=`document.querySelector('[data-order-id="${orderId}"] [aria-label="Печать ЧЗ и ШК"]')`;
        await evaluate(`${manualButton}.click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        for(let i=0;i<150&&!requestLog.some(row=>row.path.endsWith('/order-print-tape'));i++)await sleep(100);
        const tape=requestLog.find(row=>row.path.endsWith('/order-print-tape'));
        assert.equal(tape?.status,200,`selected order manual KIZ reaches tape API: ${JSON.stringify(tape)}`);
        assert.deepEqual(tape.body.order_ids,[orderId]);
        await until(`window.__AUDIT_HTML_PRINTS__.length===1`);
        const dialog=`[...document.querySelectorAll('[role="dialog"]')].find(node=>node.getClientRects().length>0&&node.querySelector('[data-testid="marking-print-confirm"]'))`;
        await until(`${dialog}`);
        const close=`[...(${dialog})?.querySelectorAll('button')??[]].find(button=>button.textContent.trim()==='Отмена')`;
        await evaluate(`${close}.click()`);
        await until(`![...document.querySelectorAll('[role="dialog"]')].some(node=>node.getClientRects().length>0&&node.querySelector('[data-testid="marking-print-confirm"]'))`);
        const boundBefore=await snapshot();
        const bindingBefore=boundBefore.markings.find(mark=>mark.order_id===orderId);
        assert(bindingBefore,'manual tape persists the exact source order binding before transfer');
        const selected=await evaluate(`${rowCheckbox}.checked`);
        if(!selected)await evaluate(`${rowCheckbox}.click()`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-more-actions"]').click()`);
        await until(`document.querySelector('[role="menu"]')&&document.querySelector('[data-testid="fbs-packing-transfer-supply"]')`);
        await evaluate(`document.querySelector('[data-testid="fbs-packing-transfer-supply"]').click()`);
        await until(`document.querySelector('[data-testid="fbs-transfer-supply-dialog"]')&&document.querySelector('[data-testid="fbs-transfer-targets"]')`);
        const targetsResponse=await requestLog.filter(row=>row.path.includes('/transfer-targets')).at(-1);
        assert.equal(targetsResponse?.status,200,'the real API returns compatible same-seller target supplies');
        await evaluate(`document.querySelector('[data-testid="fbs-transfer-target-open"]').click()`);
        const targetChoice=`document.querySelector('[data-testid="fbs-transfer-target-${targetId}"]')`;
        await until(`${targetChoice}`);
        await evaluate(`${targetChoice}.click()`);
        const transferCount=requestLog.filter(row=>row.path.endsWith('/transfer-orders')).length;
        await evaluate(`document.querySelector('[data-testid="fbs-transfer-submit"]').click()`);
        for(let i=0;i<200&&requestLog.filter(row=>row.path.endsWith('/transfer-orders')).length===transferCount;i++)await sleep(100);
        const transfer=requestLog.filter(row=>row.path.endsWith('/transfer-orders')).at(-1);
        assert.equal(transfer?.status,200,`selected transfer request succeeds: ${JSON.stringify(transfer)}`);
        assert.deepEqual(transfer.body.order_ids,[orderId],'the transfer request contains only the selected source order');
        assert.equal(transfer.body.target_supply_id,targetId,'the selected compatible target is explicit');
        assert.deepEqual(transfer.response.transferred_order_ids,[orderId],'WB adapter readback confirms the same exact order transfer');
        const after=await snapshot();
        const sourceAfter=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
        const targetAfter=await api(`/operations/fbs-supplies/${targetId}/workspace`);
        const bindingAfter=after.markings.find(mark=>mark.order_id===orderId);
        assert.equal(after.orders.find(order=>order.id===orderId)?.supply_id,targetId,'local order follows the confirmed target supply');
        assert.equal(sourceAfter.orders.some(order=>order.id===orderId),false,'source workspace no longer claims the transferred order');
        assert(targetAfter.orders.some(order=>order.id===orderId),'target workspace contains the transferred order');
        assert.deepEqual(bindingAfter,bindingBefore,'transfer preserves the exact current marking and pool-code identity');
        assert.deepEqual(after.stock,before.stock,'transfer does not move inventory balances, reservations, or stock movements');
        const providerState=await fetch(BACKEND+'/provider-state').then(response=>response.json());
        assert(providerState.transfer_events.some(event=>event.operation==='add_orders'&&event.order_ids.includes(sourceOrder.wb_order_id)),'synthetic WB receiver records the exact sent WB order id');
        assert(providerState.transfer_orders[targetBefore.supply.wb_supply_id]?.includes(sourceOrder.wb_order_id),'synthetic WB readback contains the exact transferred order under the selected target supply');
        trace.push({kind:'selected-order-transfer',orderId,targetId,before,sourceBefore,targetBefore,tape,bindingBefore,targetsResponse,transfer,after,sourceAfter,targetAfter,providerState});
        report.cases.push({id:report.currentCase,status:'PASS'});
        const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
        const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
        await writeFile(`${dir}/${artifactName}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,finalDb:after},null,2));
        console.log(JSON.stringify(report.cases.at(-1)));
        continue;
      }
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
        const expectedStickerRequests=variant==='bare-group-process'?2:1;
        assert.equal(wbRequests.length,expectedStickerRequests,'each real supply makes one product API request to the local WB sticker emulator');
        assert.deepEqual(new Set(wbRequests.flatMap(row=>row.orderIds)),new Set(seed.order_ids.map((_,i)=>800392+i)),'local WB receives the actual seeded WB order identifiers');
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
        for(let i=0;i<150&&!requestLog.some(row=>row.path.endsWith('/order-print-tape')&&row.path.includes(secondSupplyId));i++)await sleep(100);
        const secondTape=requestLog.find(row=>row.path.endsWith('/order-print-tape')
          &&row.body?.order_ids?.includes(secondOrderId));
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
        await scanLive(seed.barcode);
        for(let i=0;i<200&&printLog.length<printJobsBeforeScan+2;i++)await sleep(100);
        const scanPrints=printLog.slice(printJobsBeforeScan);
        const scanOrder=afterTaskManual.orders.find(order=>order.supply_id===seed.supply_id);
        const scanCis=afterTaskManual.markings.find(marking=>marking.order_id===scanOrder?.id)?.cis;
        assert.equal(scanPrints.length,2,'real product scanner submits exactly the two configured CHZ copies after prepare');
        assert(scanCis,'the scanned supply order has a persisted current KIZ binding');
        assert(scanPrints.every(job=>job.decoded===scanCis),
          'scanner output decodes to the scanned order current full CIS rather than an unrelated/manual-only receipt');
        const scanKeys=scanPrints.map(job=>job.job.idempotencyKey);
        assert.equal(new Set(scanKeys).size,2,'each scan copy has a distinct idempotency key');
        assert(scanKeys.some(key=>key.endsWith(':chz'))&&scanKeys.some(key=>key.endsWith(':chz:c2')),
          'two scanner copies retain their expected copy-specific idempotency keys');
        assert(blocked.every(url=>new URL(url).pathname!=='/print'),
          'no print request escaped the configured synthetic print sink');
        const rejectedMarking=afterTaskManual.markings.find(row=>row.order_id===secondOrderId);
        assert(rejectedMarking?.cis,'the task-backed order has a current CIS before rejection is configured');
        const rejection=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:secondOrderId,cis_code:rejectedMarking.cis})}).then(r=>r.json());
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
        assert.equal(providerState.wb_http_receiver.sgtinByOrder[firstWbOrder],postScan.markings.find(mark=>mark.order_id===seed.order_ids[0])?.cis,
          'the loopback HTTP receiver readback retains the first order exact full current CIS');
        assert.equal(providerState.wb_http_receiver.sgtinByOrder[secondWbOrder],postScan.markings.find(mark=>mark.order_id===secondOrderId)?.cis,
          'the loopback HTTP receiver retains the prior accepted CIS after rejecting the attempted replacement');
        assert(providerState.wb_http_receiver.requests.some(row=>row.method==='PUT'&&row.orderId===secondWbOrder&&row.status===409),
          'the loopback receiver journal records HTTP rejection for the exact second order');
        if(variant==='bare-group-process'){
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
        const scannerInventory=await evaluate(`(()=>({bars:document.querySelectorAll('[data-testid="fbs-unified-scan"]').length,globalInputs:document.querySelectorAll('[data-testid="fbs-unified-scan"] input[data-packing-scan="true"]').length,rowInputs:[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].map(input=>input.closest('[data-order-id]')?.getAttribute('data-order-id')).sort()}))()`);
        assert.equal(scannerInventory.bars,1,'group screen keeps exactly one shared scanner bar');
        assert.equal(scannerInventory.globalInputs,1,'the shared scanner bar has exactly one scanner input');
        assert.deepEqual(scannerInventory.rowInputs,[...seed.order_ids].sort(),'per-order KIZ inputs remain one per seeded order');
        await evaluate(`document.querySelector('[data-testid="fbs-packing-select-all"]').click()`);
        await until(`document.querySelectorAll('[data-order-id] input[type="checkbox"]:checked').length===2`);
        await evaluate(`[...document.querySelectorAll('button')].find(b=>/^Печать (выбранного|всего)/.test(b.textContent)).click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        await until(`window.__AUDIT_HTML_PRINTS__.length===1`);
        if(variant==='unified-rejected-filter'){
          // This variant seeds one supply with two orders. The first confirmed
          // tape is the complete batch, so its browser print dialog closes;
          // a second confirmation exists only in the multi-supply coordinator.
          const visiblePrintDialog=`[...document.querySelectorAll('[role="dialog"]')].some(dialog=>dialog.getClientRects().length>0&&dialog.querySelector('[data-testid="marking-print-confirm"]'))`;
          await until(`!${visiblePrintDialog}`);
        }else{
          await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
        }
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
        }else if(variant==='unified-rejected-filter'){
          const selectedOrderId=seed.order_ids[1];
          const preReject=await snapshot();
          const selectedMarking=preReject.markings.find(row=>row.order_id===selectedOrderId);
          assert(selectedMarking?.cis,'the selected order has an exact current CIS before provider rejection is configured');
          const rejectConfig=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:selectedOrderId,cis_code:selectedMarking.cis})}).then(response=>response.json());
          assert.equal(rejectConfig.outcome,'rejected','the local provider rejects only the exact second order after manual output');
          const checkCount=requestLog.filter(row=>row.path.endsWith('/markings/sync')).length;
          await until(`document.querySelector('[data-testid="fbs-packing-check-wb"]')&&!document.querySelector('[data-testid="fbs-packing-check-wb"]').disabled`);
          await evaluate(`document.querySelector('[data-testid="fbs-packing-check-wb"]').click()`);
          for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith('/markings/sync')).length===checkCount;i++)await sleep(100);
          const wbCheck=requestLog.filter(row=>row.path.endsWith('/markings/sync')).at(-1);
          assert.equal(wbCheck?.status,200,'the UI requests current WB status through the real local API');
          const afterCheck=await snapshot();
          const afterWorkspace=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          const statuses=afterWorkspace.orders.map(order=>({id:order.id,states:order.metadata.states.map(state=>state.status)}));
          assert(statuses.find(row=>row.id===seed.order_ids[0])?.states.includes('accepted'),'the exact first KIZ is accepted by the synthetic WB boundary');
          assert(statuses.find(row=>row.id===selectedOrderId)?.states.includes('rejected'),'the exact second KIZ is rejected by the synthetic WB boundary');
          const providerState=await fetch(BACKEND+'/provider-state').then(response=>response.json());
          for(const id of seed.order_ids){
            const order=afterWorkspace.orders.find(row=>row.id===id);
            const marking=afterCheck.markings.find(row=>row.order_id===id);
            assert.equal(providerState.wb_http_receiver.sgtinByOrder[order.wb_order_id],marking.cis,'the independent loopback receiver readback captures the exact full CIS for each WB order');
          }
          assert(providerState.wb_http_receiver.requests.some(row=>row.method==='PUT'&&row.orderId===afterWorkspace.orders.find(order=>order.id===selectedOrderId).wb_order_id&&row.status===409),'the receiver HTTP journal records the exact rejected WB order/value attempt');
          const toggle=`document.querySelector('[data-testid="fbs-wb-rejected-kiz-toggle"]')`;
          await until(`${toggle}&&${toggle}.getAttribute('aria-pressed')==='false'`);
          await evaluate(`${toggle}.click()`);
          await until(`${toggle}.getAttribute('aria-pressed')==='true'&&document.querySelector('[data-testid="fbs-wb-rejected-kiz-header"]')`);
          const filterState=await evaluate(`(()=>{const header=document.querySelector('[data-testid="fbs-wb-rejected-kiz-header"]');const rows=[...document.querySelectorAll('[data-order-id]')];return {pressed:document.querySelector('[data-testid="fbs-wb-rejected-kiz-toggle"]')?.getAttribute('aria-pressed'),header:header?.textContent.trim(),visible:rows.filter(row=>getComputedStyle(row).display!=='none').map(row=>({id:row.getAttribute('data-order-id'),highlighted:row.getAttribute('data-scan-highlighted')==='true',text:row.textContent.trim()})),allIds:rows.map(row=>row.getAttribute('data-order-id'))}})()`);
          assert.equal(filterState.pressed,'true','the actual UI exposes the filter as pressed after the operator toggles it');
          assert.match(filterState.header,/Не принятые WB КИЗ · 1/,'the rejected-only header counts exactly the one rejected order');
          assert(filterState.visible.some(row=>row.id===selectedOrderId),'the rejected second order remains visible under the filter');
          assert(filterState.visible.every(row=>row.id===selectedOrderId||row.highlighted),'only the rejected order and any explicitly pinned active scan row remain visible');
          trace.push({kind:'rejected-filter-current-provider-readback',rejectConfig,wbCheck,afterCheck,afterWorkspace,providerState,filterState});
        }else{
          await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
          await until(`window.__AUDIT_HTML_PRINTS__.length===2`);
          const tapes=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
          assert.equal(tapes.length,2,'one successful manual batch per original supply');
          for(let i=0;i<2;i++)assert.deepEqual(tapes.find(r=>r.path.includes(seed.supply_ids[i])).body.order_ids,[seed.order_ids[i]],'seller/supply never receives neighbouring order IDs');
          assert.equal((await snapshot()).markings.length,2);
          if(variant==='unified-group-packall'){
            const visiblePrintDialog=`[...document.querySelectorAll('[role="dialog"]')].find(dialog=>dialog.getClientRects().length>0&&dialog.querySelector('[data-testid="marking-print-confirm"]'))`;
            await until(`${visiblePrintDialog}`);
            const closePrint=`[...(${visiblePrintDialog})?.querySelectorAll('button')??[]].find(button=>button.textContent.trim()==='Отмена')`;
            await until(`${closePrint}&&!${closePrint}.disabled`);
            await evaluate(`${closePrint}.click()`);
            await until(`![...document.querySelectorAll('[role="dialog"]')].some(dialog=>dialog.getClientRects().length>0&&dialog.querySelector('[data-testid="marking-print-confirm"]'))`);
            const targetWorkspace=await api(`/operations/fbs-supplies/${seed.supply_ids[0]}/workspace`);
            const beforePack=await snapshot();
            await evaluate(`document.querySelector('[data-testid="fbs-packing-more-actions"]').click()`);
            await until(`document.querySelector('[role="menu"]')`);
            const targetSupplyName=targetWorkspace.supply.name;
            await evaluate(`(()=>{const item=[...document.querySelectorAll('[role="menuitem"]')].find(node=>node.textContent.includes(${JSON.stringify(targetSupplyName)}));if(!item)throw Error('target supply scope missing from actions menu');item.click()})()`);
            await until(`document.querySelector('[role="menu"]')&&[...document.querySelectorAll('[role="menuitem"]')].some(item=>item.textContent.trim()==='Всё упаковано · вся поставка')`);
            const packItemState=await evaluate(`(()=>{const item=[...document.querySelectorAll('[role="menuitem"]')].find(node=>node.textContent.trim()==='Всё упаковано · вся поставка');return {text:item?.textContent.trim(),ariaDisabled:item?.getAttribute('aria-disabled'),muiDisabled:item?.classList.contains('Mui-disabled'),scope:[...document.querySelectorAll('[role="menuitem"]')].find(node=>node.textContent.startsWith('Действия:'))?.textContent}})()`);
            assert.equal(packItemState.muiDisabled,false,'group pack-all action is enabled for the selected supply scope');
            const packCount=requestLog.filter(row=>row.path.endsWith('/pack-all-and-complete')).length;
            await evaluate(`[...document.querySelectorAll('[role="menuitem"]')].find(item=>item.textContent.trim()==='Всё упаковано · вся поставка').click()`);
            for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith('/pack-all-and-complete')).length===packCount;i++)await sleep(100);
            const packRequest=requestLog.filter(row=>row.path.endsWith('/pack-all-and-complete')).at(-1);
            assert.equal(packRequest?.status,200,`group pack-all request succeeds: ${JSON.stringify(packRequest)}`);
            const afterPack=await snapshot();
            const targetOrderIds=seed.order_ids.slice(0,1);
            assert.deepEqual(packRequest.body.order_ids,targetOrderIds,'group pack-all action is scoped to the selected supply only');
            assert(afterPack.orders.find(order=>order.id===targetOrderIds[0])?.pack_status==='packed','the selected supply order is packed');
            assert(afterPack.orders.find(order=>order.id===seed.order_ids[1])?.pack_status!=='packed','the neighboring supply order remains untouched');
            assert.deepEqual(afterPack.stock,beforePack.stock,'group pack-all updates packing state without moving stock');
            trace.push({kind:'group-scoped-pack-all',targetSupplyId:seed.supply_ids[0],targetSupplyName,packItemState,packRequest,beforePack,afterPack});
          }else if(variant==='unified-rejected-filter'){
            const selectedOrderId=seed.order_ids[1];
            const preReject=await snapshot();
            const selectedMarking=preReject.markings.find(row=>row.order_id===selectedOrderId);
            assert(selectedMarking?.cis,'the selected order has an exact current CIS before provider rejection is configured');
            const rejectConfig=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:selectedOrderId,cis_code:selectedMarking.cis})}).then(response=>response.json());
            assert.equal(rejectConfig.outcome,'rejected','the local provider rejects only the exact second order after manual output');
            const checkCount=requestLog.filter(row=>row.path.endsWith('/markings/sync')).length;
            await until(`document.querySelector('[data-testid="fbs-packing-check-wb"]')&&!document.querySelector('[data-testid="fbs-packing-check-wb"]').disabled`);
            await evaluate(`document.querySelector('[data-testid="fbs-packing-check-wb"]').click()`);
            for(let i=0;i<150&&requestLog.filter(row=>row.path.endsWith('/markings/sync')).length===checkCount;i++)await sleep(100);
            const wbCheck=requestLog.filter(row=>row.path.endsWith('/markings/sync')).at(-1);
            assert.equal(wbCheck?.status,200,'the UI requests current WB status through the real local API');
            const afterCheck=await snapshot();
            const afterWorkspace=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
            const statuses=afterWorkspace.orders.map(order=>({id:order.id,states:order.metadata.states.map(state=>state.status)}));
            assert(statuses.find(row=>row.id===seed.order_ids[0])?.states.includes('accepted'),'the exact first KIZ is accepted by the synthetic WB boundary');
            assert(statuses.find(row=>row.id===selectedOrderId)?.states.includes('rejected'),'the exact second KIZ is rejected by the synthetic WB boundary');
            const providerState=await fetch(BACKEND+'/provider-state').then(response=>response.json());
            for(const id of seed.order_ids){
              const order=afterWorkspace.orders.find(row=>row.id===id);
              const marking=afterCheck.markings.find(row=>row.order_id===id);
              assert.equal(providerState.wb_http_receiver.sgtinByOrder[order.wb_order_id],marking.cis,'the independent loopback receiver readback captures the exact full CIS for each WB order');
            }
            assert(providerState.wb_http_receiver.requests.some(row=>row.method==='PUT'&&row.orderId===afterWorkspace.orders.find(order=>order.id===selectedOrderId).wb_order_id&&row.status===409),'the receiver HTTP journal records the exact rejected WB order/value attempt');
            const toggle=`document.querySelector('[data-testid="fbs-wb-rejected-kiz-toggle"]')`;
            await until(`${toggle}&&${toggle}.getAttribute('aria-pressed')==='false'`);
            await evaluate(`${toggle}.click()`);
            await until(`${toggle}.getAttribute('aria-pressed')==='true'&&document.querySelector('[data-testid="fbs-wb-rejected-kiz-header"]')`);
            const filterState=await evaluate(`(()=>{const header=document.querySelector('[data-testid="fbs-wb-rejected-kiz-header"]');const rows=[...document.querySelectorAll('[data-order-id]')];return {pressed:document.querySelector('[data-testid="fbs-wb-rejected-kiz-toggle"]')?.getAttribute('aria-pressed'),header:header?.textContent.trim(),visible:rows.filter(row=>getComputedStyle(row).display!=='none').map(row=>({id:row.getAttribute('data-order-id'),highlighted:row.getAttribute('data-scan-highlighted')==='true',text:row.textContent.trim()})),allIds:rows.map(row=>row.getAttribute('data-order-id'))}})()`);
            assert.equal(filterState.pressed,'true','the actual UI exposes the filter as pressed after the operator toggles it');
            assert.match(filterState.header,/Не принятые WB КИЗ · 1/,'the rejected-only header counts exactly the one rejected order');
            assert(filterState.visible.some(row=>row.id===selectedOrderId),'the rejected second order remains visible under the filter');
            assert(filterState.visible.every(row=>row.id===selectedOrderId||row.highlighted),'only the rejected order and any explicitly pinned active scan row remain visible');
            trace.push({kind:'rejected-filter-current-provider-readback',rejectConfig,wbCheck,afterCheck,afterWorkspace,providerState,filterState});
          }
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
          const configured=await fetch(BACKEND+'/configure-wb-rejection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:a,cis_code:next.cis})}).then(r=>r.json());
          assert.equal(configured.outcome,'rejected','the loopback WB receiver rejects only the proposed replacement CIS');
          const replacement=await api('/operations/fbs-orders/kiz/commit','POST',{
            pairs:[{order_id:a,value:next.cis,confirmed:true}],idempotency_key:'replace-pool-audit',scan_no_wb_wait:true});
          const db=await snapshot();
          const oldCis=before.markings.find(marking=>marking.order_id===a)?.cis;
          assert(oldCis,'the order starts with an existing current CIS before replacement');
          assert(db.markings.some(m=>m.order_id===a&&m.cis===oldCis),'provider refusal restores the previous exact local CIS');
          const receiver=await(await fetch(BACKEND+'/provider-state')).json();
          const beforeWorkspace=await api(`/operations/fbs-supplies/${seed.supply_id}/workspace`);
          const wbOrder=Number(beforeWorkspace.orders.find(order=>order.id===a)?.wb_order_id);
          const wbWrites=receiver.wb_http_receiver.requests.filter(row=>row.orderId===wbOrder&&['PUT','DELETE'].includes(row.method));
          assert.deepEqual(wbWrites.map(row=>[row.method,row.status]),[['DELETE',204],['PUT',409],['PUT',204]],
            'the real WB client deletes old state, receives exact-value refusal, then restores prior state');
          assert.deepEqual(receiver.wb_http_receiver.requests.filter(row=>row.orderId===wbOrder&&row.method==='PUT').map(row=>row.body.sgtins[0]),[next.cis,oldCis],
            'the receiver journals the exact full replacement and restore CIS values in request bodies');
          assert.equal(receiver.wb_http_receiver.sgtinByOrder[wbOrder],oldCis,
            'independent receiver state readback confirms the old CIS was restored');
          trace.push({kind:'operator-replace-refusal-restore-real-loopback-wb-http',oldOrder:a,wbOrder,oldCis,nextCis:next.cis,replacement,db,receiver});
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
    }catch(e){report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});}
    const artifactName=report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
    try {
      const html=await evaluate(`(window.__AUDIT_HTML_PRINTS__||[]).join('\\n<!-- WMS666 PRINT SPLIT -->\\n')`);
      if(html)await writeFile(`${dir}/${artifactName}.html`,html);
      const screenshot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
      await writeFile(`${dir}/${artifactName}.png`,Buffer.from(screenshot.data,'base64'));
    } catch(e) { trace.push({kind:'browser-artifact-error',error:String(e)}); }
    console.log(JSON.stringify(report.cases.at(-1)));
    await writeFile(`${dir}/${artifactName}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,finalDb:await snapshot()},null,2));
  }
}finally{
  report.productSha=process.env.WMS666_PRODUCT_SHA || null;report.externalApi='SYNTHETIC_WB_AND_PRINT;REAL_LOCAL_API_POSTGRES';
  await writeFile(`${dir}/result.json`,JSON.stringify(report,null,2));
  await writeFile(`${dir}/chrome.log`,chromeLog);cdp?.ws.close();chrome.kill();
}
process.exit(report.cases.some(c=>c.status==='FAIL')?1:0);
