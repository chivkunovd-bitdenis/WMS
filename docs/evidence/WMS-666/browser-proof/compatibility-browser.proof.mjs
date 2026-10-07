// WMS652 critical real-screen contracts. No mocked product controllers.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const bwip = require('bwip-js'), { PNG } = require('pngjs');
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, DataMatrixReader } = require('@zxing/library');
// Decode pixels handed to native print independently of the product renderer/claim.
// The canonical 60x80 fixture's matrix occupies the top 44%; text below must not
// confuse the detector. A swapped, truncated or different full CIS is a failure.
function decodedPngDataUrl(dataUrl){
  const png=PNG.sync.read(Buffer.from(dataUrl.split(',')[1],'base64'));
  const height=Math.floor(png.height*.44), pixels=new Uint8ClampedArray(png.width*height);
  for(let i=0;i<pixels.length;i++)pixels[i]=(png.data[4*i]+2*png.data[4*i+1]+png.data[4*i+2])/4;
  return new DataMatrixReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,png.width,height)))).getText();
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
let seed, held, pausePoint='', pausedOnce=false, failDeleteOnce=false, failTapeSupplyId='', failTapeOnce=false;
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
  return sources.map(images=>images.map(decodedPngDataUrl));
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
  async function forward(){
    const r=await fetch(BACKEND+'/proxy'+path+u.search,{method:request.method,headers:{'Content-Type':'application/json'},...(request.postData?{body:request.postData}:{})});
    const bytes=Buffer.from(await r.arrayBuffer());let response;
    try{response=JSON.parse(bytes.toString())}catch{response={binary:bytes.length}}
    requestLog.push({method:request.method,path:path+u.search,body,status:r.status,response});
    return {bytes,status:r.status,type:r.headers.get('Content-Type')||'application/json'};
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
  '--disable-background-networking',`--remote-debugging-port=${process.env.WMS666_CDP_PORT || '16707'}` ,
  `--user-data-dir=${mkdtempSync(`${tmpdir()}/wms666-live-audit-`)}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='';chrome.stderr.on('data',d=>chromeLog+=d);
try{
  let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch(`http://127.0.0.1:${process.env.WMS666_CDP_PORT || '16707'}/json/list`)).json();break}catch{await sleep(100)}}
  assert(tabs?.length,'isolated Chrome startup');cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  cdp.on('Fetch.requestPaused',interceptLive);cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',JSON.stringify({printQr:false,printChz:true,reprintChz:false,printChzCopies:2,reprintChzCopies:2}));localStorage.setItem('wms.print.labelSizeId','60x80');const q=new URLSearchParams(location.search),id=q.get('supply_id')||q.get('supply_ids');sessionStorage.setItem('wms:fbs:'+id+':stage','packing');sessionStorage.setItem('wms:fbs:assembly:'+id+':stage','packing');`});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__WMS_CAPTURE_PRINT_HTML__=true;window.__AUDIT_HTML_PRINTS__=[];window.open=()=>null;window.print=()=>{try{top.__AUDIT_HTML_PRINTS__.push(document.documentElement.outerHTML)}catch{}};`});
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  const variants=(process.env.WMS666_VARIANTS||'normal,delete-before-claim,delete-after-claim').split(',');
  for(const entry of (process.env.WMS666_ENTRIES||'supply_id,supply_ids').split(','))for(const variant of variants){
    await cdp.send('Page.navigate',{url:'about:blank'});await sleep(500);
    for(let i=0;i<100;i++){if((await(await fetch(BACKEND+'/idle')).json()).active===0)break;await sleep(100)}
    report.currentCase=variant==='ozon-scope'?'WMS666.ozon-scope.actual-react-postgres'
      :variant.startsWith('unified-')?`WMS666.M41.${variant.slice('unified-'.length)}`
      :`WMS666.actualPool[${entry};${variant}]`;
    requestLog=[];printLog=[];trace=[];blocked=[];errors=[];held=null;pausedOnce=false;failTapeSupplyId='';failTapeOnce=false;
    pausePoint=/^(delete|replace)-/.test(variant)?(variant.endsWith('before-claim')?'before-claim':'after-claim'):'';
    if(variant==='manual-then-delete-scan')pausePoint='manual-response';
    if(variant.endsWith('-after-validation'))pausePoint='after-validation';
    if(variant==='rapid-scans'||variant==='multi-seller'||variant==='flags-after-claim')pausePoint='after-claim';
    const seedPath=variant==='ozon-scope'?'/seed-ozon':'/seed';
    seed=await(await fetch(BACKEND+seedPath,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes:variant.startsWith('unified-')||variant==='ozon-scope'||variant==='clear-partial'||variant==='controls'||variant==='rapid-scans'||variant==='multi-seller'||variant.startsWith('manual-')?4:variant.startsWith('replace')?2:1,multi:variant==='multi-seller'||variant.startsWith('unified-'),stickers:qrImages.map(p=>p.toString('base64'))})})).json();
    try{
      if(variant==='clear-partial')await api(`/operations/fbs-supplies/${seed.supply_id}/order-print-tape`,'POST',{order_ids:seed.order_ids,layout_json:{units:[{block:'cz',copies:1}]},include_order_qr:false,reprint:false,allow_partial:false});
      await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs?${entry}=${seed.supply_ids.join(',')}`});
      await until(`document.querySelector('[data-order-id="${seed.order_ids[0]}"]')&&document.querySelector('[data-packing-scan]')`);
      if(variant==='ozon-scope'){
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
