import { createWorkspaceContextObserver } from './identity-observer.untracked.mjs';
const errorContext=createWorkspaceContextObserver();
// WMS652 critical real-screen contracts. No mocked product controllers.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { workspace, selectionFixtures } from './fixtures.mjs';
import { geometryContracts } from './geometry.mjs';
const require = createRequire(new URL('../../package.json', import.meta.url));
const bwip = require('bwip-js'), { PNG } = require('pngjs');
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, DataMatrixReader } = require('@zxing/library');
// Decode pixels handed to native print independently of the product renderer/claim.
// The canonical 60x80 fixture's matrix occupies the top 44%; text below must not
// confuse the detector. A swapped, truncated or different full CIS is a failure.
function decodedCis(job){
  const png=PNG.sync.read(Buffer.from(job.imageDataUrl.split(',')[1],'base64'));
  const height=Math.floor(png.height*.44), pixels=new Uint8ClampedArray(png.width*height);
  for(let i=0;i<pixels.length;i++)pixels[i]=(png.data[4*i]+2*png.data[4*i+1]+png.data[4*i+2])/4;
  return new DataMatrixReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,png.width,height)))).getText();
}
const ORIGIN = 'http://127.0.0.1:16686';
const dir = process.env.WMS652_EVIDENCE;
if (!dir) throw Error('Set WMS652_EVIDENCE to a persistent evidence directory');
await mkdir(dir,{recursive:true});
const qrCodes = ['*DUIkWJJF', '*DUIkNEXT'];
const cises = ['010460000000000121SERIAL-A\u001d91ABCD\u001d92signed-A','010460000000000221SERIAL-B\u001d91EFGH\u001d92signed-B'];
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
      try { errorContext.message(this,msg); } catch { errorContext.observerFailure(); }
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
    try { errorContext.command(this,{id,method,params,identity}); } catch { errorContext.observerFailure(); }
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
function prepareState(many) {
  state = {'wb-a':workspace('wb-a','wb'),'wb-b':workspace('wb-b','wb')};
  const a=state['wb-a'].orders[0], b=state['wb-b'].orders[0];
  a.sticker.code=qrCodes[0]; b.sticker.code=qrCodes[1];
  a.metadata.required=b.metadata.required=['sgtin'];
  b.id='wb-next-order'; b.product.id='product-next'; b.wb_order_id=666002;
  if(!many){ b.supply_id='wb-a';state['wb-a'].orders.push(b); }
  for(const w of Object.values(state)) w.boxes=[];
}
function bindingTarget(one){return {order_id:one.id,wb_order_id:one.wb_order_id,product:one.product,
 current_kiz:null,needs_confirmation:false,can_bind:true,block_reason:null,requires_honest_sign:true};}
async function intercept({requestId,request}) {
  const u=new URL(request.url),path=u.pathname.replace(/^\/api/,'');
  if(u.origin===ORIGIN&&!u.pathname.startsWith('/api/')&&!path.startsWith('/assets/qr-'))return cdp.send('Fetch.continueRequest',{requestId});
  if(u.origin==='http://127.0.0.1:17843'&&path==='/print'){
    if(request.method==='OPTIONS')return fulfill(requestId,{});
    const job=JSON.parse(request.postData);printLog.push(job);trace.push(`print:${job.idempotencyKey}`);
    const key=job.idempotencyKey;
    if(!acceptedPrints.has(key))acceptedPrints.set(key,{job,receipt:`synthetic-${acceptedPrints.size+1}`});
    if(receiptMode==='held'&&printLog.length===1){heldPrint=()=>fulfill(requestId,{receipt:acceptedPrints.get(key).receipt});return;}
    if(receiptMode==='lost'&&!lostAck){lostAck=true;return cdp.send('Fetch.failRequest',{requestId,errorReason:'ConnectionClosed'});}
    return fulfill(requestId,{receipt:acceptedPrints.get(key).receipt});
  }
  if(u.origin!==ORIGIN){blocked.push(request.url);return cdp.send('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'});}
  const body=request.postData?JSON.parse(request.postData):null;
  requestLog.push({method:request.method,path:path+u.search,body});
  const ws=path.match(/^\/operations\/fbs-supplies\/([^/]+)\/workspace$/);
  if(ws)return fulfill(requestId,state[ws[1]]);
  if(mode==='geometry-list'&&path==='/operations/fbs-orders/worklist')return fulfill(requestId,{items:selectionState.orders,total:selectionState.orders.length,warehouse_options:[],server_now:'2026-10-06T08:00:00Z'});
  const documentRead=path.match(/^\/operations\/fbs-orders\/([^/]+)\/ozon-exemplar-documents$/);
  if(mode==='geometry-packing'&&documentRead&&request.method==='GET'){
    const one=Object.values(state).flatMap(w=>w.orders).find(o=>o.id===documentRead[1]);
    assert(one?.marketplace==='ozon','documents reader belongs to the actual Ozon order');
    return fulfill(requestId,{version:1,state:'editable',absence_selected:false,requirements_complete:true,errors:[],
      products:(one.positions.length?one.positions:[one.product]).map((_,i)=>({product_id:663001+i,
        exemplars:[{exemplar_id:91+i,gtd_required:false,rnpt_required:false,is_gtd_absent:false,is_rnpt_absent:false}]}))});
  }
  if(path.endsWith('/pick-options')||path==='/products/linked-wb-catalog')return fulfill(requestId,[]);
  if(path.endsWith('/print-assets'))return fulfill(requestId,{items:[],ready:0,total:0,errors:[]});
  if(mode==='selection'&&path.startsWith('/operations/'))return selectionBoundary(requestId,request.method,path,u,body);
  if(path.endsWith('/worklist')||path==='/operations/fbs-assembly-tasks')return fulfill(requestId,{items:[],total:0,warehouse_options:[],server_now:'2026-10-06T08:00:00Z'});
  if(path==='/auth/me')return fulfill(requestId,{separate_marking_print_enabled:false});
  if(path==='/fbs/assembly-time')return fulfill(requestId,{hours:0,orders:0});
  if(path.endsWith('/order-print-tape'))return fulfill(requestId,{orders:[],order_errors:[],shortage:0});
  const lookup=path==='/operations/fbs-orders/kiz/lookup';
  if(lookup){
    const one=state[u.searchParams.get('supply_id')]?.orders.find(o=>o.sticker.code===u.searchParams.get('sticker'));
    if(!one)return fulfill(requestId,{detail:{code:'sticker_not_found',message:'Стикер не найден'}},404);
    trace.push(`lookup:${one.id}`);
    if(holdFirst&&one.id==='wb-a-order'){heldLookup=()=>fulfill(requestId,bindingTarget(one));return;}
    return fulfill(requestId,bindingTarget(one));
  }
  const scan=path.match(/^\/operations\/fbs-supplies\/([^/]+)\/scan-auto-print$/);
  if(scan){
    if(!body.order_id){trace.push(`product-miss:${body.barcode}`);return fulfill(requestId,{detail:{code:'scan_product_not_found',message:'Не товарный ШК'}},404);}
    const one=state[scan[1]].orders.find(o=>o.id===body.order_id);
    assert(one&&one.sticker.code===body.barcode,'wrong sticker selection object');
    trace.push(`select:${one.id}`);
    return fulfill(requestId,{scan_id:`scan-${one.id}`,order_id:one.id,wb_order_id:one.wb_order_id,
      replayed:restored,binding_target:bindingTarget(one),reprint_recovery:restored&&boundOrders.has(one.id)?{status:'available',kiz:boundOrders.get(one.id),code_id:null,has_label_artifact:false}:null,requires_honest_sign:true,
      qr_asset:{id:`qr-${one.id}`,kind:'order_sticker',status:'ready',content_type:'image/png',width_mm:58,height_mm:40,
        preview_url:`/assets/qr-${one.id}.png`,download_url:null,checksum:null,applied_at:null,error:null},
      codes:[],printed_codes:[],shortage:0,order_errors:[]});
  }
  if(path.startsWith('/assets/qr-'))return fulfill(requestId,qrImages[path.includes('wb-a-order')?0:1],200,'image/png');
  if(path==='/operations/fbs-orders/kiz/validate')return fulfill(requestId,{valid:true});
  if(path==='/operations/fbs-orders/kiz/commit'){
    trace.push(`bind:${body.pairs[0].order_id}`);boundOrders.set(body.pairs[0].order_id,body.pairs[0].value);
    return fulfill(requestId,body.pairs.map(p=>({order_id:p.order_id,status:'ok',code:'ok',bound_kiz:p.value})));
  }
  const copy=path.match(/\/scan-auto-print\/scan-(.+)\/reprint-claim$/);
  if(copy)return fulfill(requestId,{claimed:true,started:false,kiz:cises[copy[1]==='wb-a-order'?0:1],code_id:null,has_label_artifact:false});
  if(path.endsWith('/print-claim'))return fulfill(requestId,{claimed:true,started:false});
  if(path.endsWith('/print-started'))return fulfill(requestId,{claimed:false,started:true});
  const task=path.match(/^\/operations\/packaging-tasks\/task-([^/]+)$/);
  if(task)return fulfill(requestId,{id:`task-${task[1]}`,document_number:task[1],display_number:task[1],status:'in_progress',
    lines:state[task[1]].orders.map(o=>({id:`line-${o.id}`,product_id:o.product.id,product_name:o.product.name,
      sku_code:o.product.sku,requires_honest_sign:true,packaging_instructions:'',qty_total:1,qty_need_pack:1,marking_available_count:mode==='geometry-packing'?2:0}))});
  if(path.endsWith('/pack')){trace.push(`pack:${body.order_id}`);return fulfill(requestId,{});}
  return fulfill(requestId,{detail:{code:'unhandled_synthetic_endpoint',message:path}},404);
}
async function scan(code) {
  await until(`document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]')&&!document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]').disabled`,5000);
  await evaluate(`document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]').focus()`);
  await cdp.send('Input.insertText',{text:code});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
}
const chromePath=process.env.WMS652_CHROME||(process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':'google-chrome');
const chrome=spawn(chromePath,['--headless=new','--mute-audio','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update',
 '--remote-debugging-port=16687',`--user-data-dir=${mkdtempSync(`${tmpdir()}/wms652-critical-chrome-`)}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='';chrome.stderr.on('data',d=>{chromeLog+=d});chrome.stdout.on('data',d=>{chromeLog+=d});chrome.on('error',e=>{chromeLog+=String(e)});
try {
  let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch('http://127.0.0.1:16687/json/list')).json();break}catch{await sleep(100)}}
  assert(tabs?.length,`Chrome unavailable: ${chromeLog}`);
  cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);cdp.on('Fetch.requestPaused',intercept);
  cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
  await errorContext.install(cdp);
  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`
    const q=new URLSearchParams(location.search);
    if(!q.has('preserve')){localStorage.clear();sessionStorage.clear();}
    const flags={alloff:{printQr:false,printChz:false,reprintChz:false},qr:{printQr:true,printChz:false,reprintChz:false},reprint:{printQr:false,printChz:false,reprintChz:true},'qr+reprint':{printQr:true,printChz:false,reprintChz:true},pool:{printQr:false,printChz:true,reprintChz:false},'qr+pool':{printQr:true,printChz:true,reprintChz:false}};
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',JSON.stringify({...flags[q.get('flag')||'qr+reprint'],reprintChzCopies:2,printChzCopies:2}));
    localStorage.setItem('wms.print.labelSizeId','60x80');
    const p=new URLSearchParams(location.search),ids=(p.get('supply_ids')||p.get('supply_id')||'').split(',');
    sessionStorage.setItem('wms:fbs:assembly:'+ids.join(',')+':stage','packing');
    ids.forEach(id=>sessionStorage.setItem('wms:fbs:'+id+':stage','packing'));
  `});
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  for(const [id,query,many] of [['supply_id=A','supply_id=wb-a',false],['supply_ids=A','supply_ids=wb-a',false],['supply_ids=A,B','supply_ids=wb-a,wb-b',true]]){
    try {
    prepareState(many);requestLog=[];printLog=[];trace=[];blocked=[];errors=[];heldLookup=undefined;holdFirst=true;
    report.currentCase=`WMS652.realQr[${id}]`;
    await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs?${query}`});
    await until(`document.querySelector('[data-order-id="wb-a-order"]')&&document.querySelector('[data-testid="fbs-unified-scan"]')`);
    await scan(qrCodes[0]);
    for(let i=0;i<50&&!heldLookup;i++)await sleep(100);
    assert(heldLookup,'input must reach product-miss then sticker lookup');
    await scan(cises[0]);await scan(qrCodes[1]);await scan(cises[1]);
    await heldLookup();
    for(let i=0;i<100&&!trace.includes('pack:wb-next-order');i++)await sleep(100);
    assert(trace.includes('pack:wb-next-order'),`next QR/KIZ did not complete: ${trace.join(' -> ')}`);
    const selections=requestLog.filter(r=>r.path.endsWith('/scan-auto-print')&&r.body?.order_id);
    assert.deepEqual(selections.map(r=>r.body.order_id),['wb-a-order','wb-next-order']);
    assert.deepEqual(selections.map(r=>r.body.barcode),qrCodes);
    assert.deepEqual(selections.map(r=>r.body.print_chz),[false,false]);
    const commits=requestLog.filter(r=>r.path==='/operations/fbs-orders/kiz/commit');
    assert.deepEqual(commits.map(r=>r.body.pairs),[
      [{order_id:'wb-a-order',value:cises[0],confirmed:false,scan_auto_print_id:'scan-wb-a-order'}],
      [{order_id:'wb-next-order',value:cises[1],confirmed:false,scan_auto_print_id:'scan-wb-next-order'}],
    ]);
    assert(commits.every(r=>r.body.scan_no_wb_wait===true));
    assert.deepEqual(printLog.map(p=>p.idempotencyKey),['scan-wb-a-order','scan-wb-a-order:copy','scan-wb-a-order:copy:c2',
      'scan-wb-next-order','scan-wb-next-order:copy','scan-wb-next-order:copy:c2']);
    assert.deepEqual(printLog.map(p=>[p.widthMm,p.heightMm]),Array(6).fill([60,80]));
    assert.equal(printLog[0].imageDataUrl,`data:image/png;base64,${qrImages[0].toString('base64')}`);
    assert.equal(printLog[3].imageDataUrl,`data:image/png;base64,${qrImages[1].toString('base64')}`);
    for(const [index,cis] of [[1,cises[0]],[2,cises[0]],[4,cises[1]],[5,cises[1]]])assert.equal(decodedCis(printLog[index]),cis,'native copy must encode full canonical CIS of this order');
    assert.equal(printLog[1].imageDataUrl,printLog[2].imageDataUrl);assert.equal(printLog[4].imageDataUrl,printLog[5].imageDataUrl);
    assert.notEqual(printLog[1].imageDataUrl,printLog[4].imageDataUrl,'different canonical CIS must yield different exact copies');
    for(const index of [1,4]){const image=PNG.sync.read(Buffer.from(printLog[index].imageDataUrl.split(',')[1],'base64'));assert.equal(image.width,720);assert.equal(image.height,960);}
    const packs=requestLog.filter(r=>r.path.endsWith('/pack'));
    assert.deepEqual(packs.map(r=>r.body),[{quantity:1,order_id:'wb-a-order',idempotency_key:'scan-wb-a-order:packed'},
      {quantity:1,order_id:'wb-next-order',idempotency_key:'scan-wb-next-order:packed'}]);
    assert.deepEqual(packs.map(r=>r.path),['/operations/packaging-tasks/task-wb-a/lines/line-wb-a-order/pack',
      `/operations/packaging-tasks/task-${many?'wb-b':'wb-a'}/lines/line-wb-next-order/pack`]);
    assert.deepEqual(trace.filter(x=>x.startsWith('product-miss:')),qrCodes.map(q=>`product-miss:${q}`));
    assert(trace.indexOf('print:scan-wb-a-order')<trace.indexOf('pack:wb-a-order'));
    assert(trace.indexOf('pack:wb-a-order')<trace.indexOf('lookup:wb-next-order'));
    assert(trace.indexOf('print:scan-wb-next-order:copy:c2')<trace.indexOf('pack:wb-next-order'));
    assert.equal(blocked.length,0);assert.equal(errors.length,0);
    await writeFile(`${dir}/${id.replaceAll(/[=,]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
    report.cases.push({id:report.currentCase,status:'PASS'});console.log(`${report.currentCase}: PASS`);
    } catch(e) {
      report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});
      await writeFile(`${dir}/${id.replaceAll(/[=,]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
      console.error(`${report.currentCase}: ${e}`);
    }
  }
  await selectionContracts();
  await flagContracts();
  await geometryContracts({cdp,evaluate,until,click,clickElement,report,dir,origin:ORIGIN,
    startPacking(data){mode='geometry-packing';state={...state,...data};resetGeometry();},
    startSelection(data,list=false){mode=list?'geometry-list':'selection';selectionState=data;failedGroup='';groupAttempts={};addAttempts=0;createdRefs=[];heldAdd=undefined;resetGeometry();},
    logs:()=>({requestLog,printLog,trace,blocked,errors}),
  });
  assert(report.cases.every(one=>one.status==='PASS'),'one or more real-screen cases failed');
  assert.deepEqual(report.cases.map(one=>one.id),JSON.parse(readFileSync(new URL('./cases.json',import.meta.url),'utf8')),'complete exact browser IDs must execute');
  report.status='PASS';
}catch(e){if(report.currentCase&&!report.cases.some(one=>one.id===report.currentCase))report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});report.status='FAIL';report.failure=String(e);report.stack=e.stack;console.error(e);process.exitCode=1;}
finally{
  await writeFile(`${dir}/error-context.json`,errorContext.serialize(cdp,report));
  await writeFile(`${dir}/cdp-transport.json`,JSON.stringify({events:cdp?.transport ?? [],pendingCommandIds:[...cdp?.pending.keys() ?? []]},null,2));
  await writeFile(`${dir}/result.json`,JSON.stringify(report,null,2));
  await writeFile(`${dir}/last-requests.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
  await writeFile(`${dir}/chrome.log`,chromeLog);cdp?.ws.close();chrome.kill();
}
// True OrdersScreen selection and true create/group/add dialogs: only HTTP is synthetic.
async function selectionBoundary(requestId,method,path,u,body){
  const page=items=>({items,total:items.length,warehouse_options:[],server_now:'2026-10-06T08:00:00Z'});
  if(path==='/operations/fbs-orders/worklist')return fulfill(requestId,page(u.searchParams.get('status_group')==='new'?selectionState.orders:[]));
  if(path==='/operations/fbs-supplies/worklist')return fulfill(requestId,page(selectionState.supplies));
  if(path==='/operations/fbs-assembly-tasks'){
    if(method==='POST')return fulfill(requestId,{id:`assembly-${requestLog.length}`,number:'000652',created_at:'2026-10-06T08:00:00Z',
      created_by:{id:'tester',name:'Тестировщик'},supplies:body.supply_ids.map(id=>({id,marketplace:'wb',name:id,seller:{id:'seller-a',name:'Альфа'},
        status:'draft',orders_count:1,picked_count:0,units_count:1,picked_units_count:0,packed_count:0}))});
    return fulfill(requestId,{items:[]});
  }
  if(path==='/operations/fbs-supplies/preflight'){
    const one=selectionState.orders.find(o=>o.id===body.order_ids[0]);
    return fulfill(requestId,{compatible:true,issues:[],summary:{marketplace:'wb',seller:one.seller,wb_warehouse:one.wb_warehouse,
      wms_warehouse:one.wms_warehouse,orders_count:body.order_ids.length,cargo_type:'mgt',buyer_type:'individual',required_marking_count:0,pvz_blocked_count:0}});
  }
  if(path==='/operations/fbs-supplies/from-orders'){
    const key=body.order_ids.join(',');groupAttempts[key]=(groupAttempts[key]||0)+1;
    if(key===failedGroup&&groupAttempts[key]===1)return fulfill(requestId,{detail:{code:'fixture_refused',message:'synthetic definite refusal',retryable:false}},422);
    const id=`created-${key.replaceAll(',','-')}`;createdRefs.push(id);
    state[id]=workspace(id,'wb');state[id].orders=[];state[id].supply.packaging_task_id=null;state[id].stage='composition';
    return fulfill(requestId,state[id],201);
  }
  if(path==='/operations/fbs-supplies/compatible/orders/batch'){
    addAttempts++;
    if(addAttempts===1){heldAdd=()=>fulfill(requestId,{detail:{code:'fixture_refused',message:'synthetic definite refusal',retryable:false}},422);
      return;}
    state.compatible=workspace('compatible','wb');state.compatible.orders=[];state.compatible.stage='composition';state.compatible.supply.packaging_task_id=null;
    return fulfill(requestId,state.compatible);
  }
  if(path.endsWith('/cargo-places'))return fulfill(requestId,[]);
  return fulfill(requestId,{detail:{code:'unhandled_synthetic_endpoint',message:path}},404);
}
async function clickElement(expression, label, allowDisabled=false){
  await until(expression);
  let point;
  for(let i=0;i<40;i++){
    point=await evaluate(`(()=>{const el=${expression};el.scrollIntoView({block:'center',inline:'center'});
      const r=el.getBoundingClientRect(),s=getComputedStyle(el),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
      return {x,y,visible:r.width>0&&r.height>0&&s.display!=='none'&&s.visibility==='visible'&&Number(s.opacity)>0&&x>=0&&y>=0&&x<innerWidth&&y<innerHeight,
        reachable:hit===el||el.contains(hit)||(${allowDisabled}&&el.disabled&&hit?.contains(el)),disabled:Boolean(el.disabled)};})()`);
    if(point.visible&&point.reachable&&(!point.disabled||allowDisabled))break;
    await sleep(50);
  }
  assert(point.visible&&point.reachable&&(!point.disabled||allowDisabled),`action must have visible unobscured bounds: ${label}; ${JSON.stringify(point)}`);
  await cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:point.x,y:point.y});
  await cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});
  await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});
}
async function click(selector,allowDisabled=false){await clickElement(`document.querySelector(${JSON.stringify(selector)})`,selector,allowDisabled);}
async function freshSelection(id){
  mode='selection';selectionState=selectionFixtures();state={...state};failedGroup='';groupAttempts={};addAttempts=0;createdRefs=[];heldAdd=undefined;
  requestLog=[];printLog=[];blocked=[];errors=[];trace=[];report.currentCase=id;
  await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs`});
  await until(`document.querySelector('[data-testid="fbs-order-order-a"] input[type=checkbox]')`);
}
async function select(ids){for(const id of ids)await clickElement(`document.querySelector('[data-testid="fbs-order-${id}"] input[type=checkbox]').closest('[class*="MuiCheckbox-root"]')`,`visible checkbox ${id}`);}
async function saveCase(id){
  assert.equal(blocked.length,0);assert.equal(errors.length,0);
  await writeFile(`${dir}/${id.replaceAll(/[^A-Za-z0-9_-]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
  report.cases.push({id,status:'PASS'});console.log(`${id}: PASS`);
}
async function openCreate(){await clickElement(`[...document.querySelectorAll('[data-testid="fbs-selection-bar"] button')].find(b=>b.innerText==='Сформировать поставку')`,'Сформировать поставку');}
async function selectionContracts(){
  const one='WMS652.selection[single-create]';await freshSelection(one);await select(['order-a2','order-a']);
  await click('[data-testid="fbs-selected-open"]');
  await until(`document.querySelector('[data-testid="fbs-selected-list"]')`);
  const text=await evaluate(`document.querySelector('[data-testid="fbs-selected-list"]').innerText`);
  assert(text.includes('Товар order-a2')&&text.includes('Товар order-a'));assert(!text.includes('Товар unselected'));assert(!text.includes('Товар order-b'));
  await clickElement(`[...document.querySelectorAll('[role=dialog] button')].find(b=>b.innerText==='Закрыть')`,'Закрыть selected popup');
  await openCreate();await until(`document.querySelector('[data-testid="fbs-create-submit"]')&&!document.querySelector('[data-testid="fbs-create-submit"]').disabled`);
  const preflight=requestLog.filter(r=>r.path==='/operations/fbs-supplies/preflight');
  assert(preflight.length>0);assert.deepEqual(preflight.at(-1).body.order_ids,['order-a2','order-a']);
  await click('[data-testid="fbs-create-submit"]');
  for(let i=0;i<50&&!createdRefs.length;i++)await sleep(100);
  assert.deepEqual(requestLog.filter(r=>r.path==='/operations/fbs-supplies/from-orders').map(r=>r.body.order_ids),[['order-a2','order-a']]);
  assert.deepEqual(createdRefs,['created-order-a2-order-a']);await saveCase(one);

  const grouped='WMS652.selection[seller-warehouse-group-retry]';await freshSelection(grouped);failedGroup='order-b';
  await select(['order-b','order-c','order-a']);await openCreate();
  await until(`document.querySelector('[data-testid="fbs-group-create-submit"]')&&!document.querySelector('[data-testid="fbs-group-create-submit"]').disabled`);
  assert.equal(await evaluate(`document.querySelectorAll('[data-testid^="fbs-group-create-row-"]').length`),3);
  assert.deepEqual(requestLog.filter(r=>r.path==='/operations/fbs-supplies/preflight').map(r=>r.body.order_ids),[['order-a'],['order-c'],['order-b']]);
  await click('[data-testid="fbs-group-create-submit"]');
  await until(`document.querySelector('[data-testid="fbs-group-create-submit"]')?.innerText.includes('Повторить (1)')`);
  assert.deepEqual(createdRefs,['created-order-a','created-order-c']);
  // The selected IDs remain until all groups succeeded; successful groups
  // are retained by the real dialog and never posted again on retry.
  assert(await evaluate(`document.querySelector('[data-testid="fbs-selection-bar"]').innerText.includes('3')`));
  await click('[data-testid="fbs-group-create-submit"]');
  for(let i=0;i<50&&createdRefs.length!==3;i++)await sleep(100);
  const requestedGroups=requestLog.filter(r=>r.path==='/operations/fbs-supplies/from-orders').map(r=>r.body.order_ids.join(','));
  assert.equal(requestedGroups.length,4);assert.deepEqual(requestedGroups.slice(0,3).sort(),['order-a','order-b','order-c']);assert.equal(requestedGroups[3],'order-b');
  assert.deepEqual([...createdRefs].sort(),['created-order-a','created-order-b','created-order-c']);
  for(let i=0;i<50&&requestLog.filter(r=>r.method==='POST'&&r.path==='/operations/fbs-assembly-tasks').length<2;i++)await sleep(100);
  assert.deepEqual(requestLog.filter(r=>r.method==='POST'&&r.path==='/operations/fbs-assembly-tasks').map(r=>r.body.supply_ids),[['created-order-a','created-order-c'],['created-order-b']]);
  await saveCase(grouped);

  const add='WMS652.selection[add-existing-refusal-retry]';await freshSelection(add);await select(['order-a2','order-a']);
  await click('[data-testid="fbs-05-add-existing-open"]');
  await until(`document.querySelector('[data-testid="fbs-05-existing-supply-select"] [role=combobox]')`);
  await evaluate(`document.querySelector('[data-testid="fbs-05-existing-supply-select"] [role=combobox]').focus()`);
  await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
  await until(`document.querySelector('[role=listbox]')`);
  const options=await evaluate(`[...document.querySelectorAll('[role=listbox] [role=option]')].map(o=>o.dataset.value)`);
  assert.deepEqual(options,['compatible']);await click('[role=option][data-value="compatible"]');
  await click('[data-testid="fbs-05-add-existing-submit"]');
  for(let i=0;i<50&&!heldAdd;i++)await sleep(100);
  assert(heldAdd,'add HTTP boundary not reached');
  assert.equal(await evaluate(`document.querySelector('[data-testid="fbs-05-add-existing-submit"]').disabled`),true);
  await click('[data-testid="fbs-05-add-existing-submit"]',true);assert.equal(addAttempts,1,'busy button must not add twice');
  await heldAdd();await until(`document.querySelector('[data-testid="fbs-add-existing-error"]')`);
  assert.equal(await evaluate(`document.querySelector('[data-testid="fbs-order-order-a"] input').checked`),true);
  assert.equal(await evaluate(`document.querySelector('[data-testid="fbs-order-order-a2"] input').checked`),true);
  await click('[data-testid="fbs-05-add-existing-submit"]');
  for(let i=0;i<50&&addAttempts!==2;i++)await sleep(100);
  assert.deepEqual(requestLog.filter(r=>r.path==='/operations/fbs-supplies/compatible/orders/batch').map(r=>r.body.order_ids),[['order-a2','order-a'],['order-a2','order-a']]);
  assert.equal(addAttempts,2,'one refused and one successful explicit add, with no silent repeat');
  await saveCase(add);
}

// Six agreed WB checkbox combinations and three uncertain receipt recoveries.
async function flagContracts(){
  const entries=[['supply_id=A','supply_id=wb-a',false],['supply_ids=A','supply_ids=wb-a',false],['supply_ids=A,B','supply_ids=wb-a,wb-b',true]];
  const variants=['alloff','qr','reprint','qr+reprint','pool','qr+pool','held-receipt','lost-accepted-ack','remount-after-lost-ack'];
  for(const variant of variants)for(const [entry,query,many] of entries){
    mode='qr';prepareState(many);requestLog=[];printLog=[];trace=[];blocked=[];errors=[];
    heldLookup=undefined;holdFirst=false;heldPrint=undefined;acceptedPrints=new Map();boundOrders=new Map();restored=false;lostAck=false;
    const recovery=['held-receipt','lost-accepted-ack','remount-after-lost-ack'].includes(variant);
    const flag=recovery?'qr':variant, qr=flag.includes('qr'), copy=flag.includes('reprint'), server=qr||copy;
    receiptMode=variant==='held-receipt'?'held':recovery?'lost':'';
    report.currentCase=`WMS652.realQrFlags[${variant};${entry}]`;
    const url=`${ORIGIN}/app/ff/fbs?${query}&flag=${encodeURIComponent(flag)}`;
    try{
      await cdp.send('Page.navigate',{url});
      await until(`document.querySelector('[data-order-id="wb-a-order"]')&&document.querySelector('[data-testid="fbs-unified-scan"]')`);
      await scan(qrCodes[0]);
      for(let i=0;i<70&&!trace.includes('lookup:wb-a-order');i++)await sleep(100);
      assert(trace.includes('lookup:wb-a-order'),'real input must reach correct sticker lookup');
      await scan(cises[0]);
      if(variant==='held-receipt'){
        for(let i=0;i<70&&!heldPrint;i++)await sleep(100);
        assert(heldPrint,'native print must reach held accepted receipt');
        await scan(qrCodes[1]);await scan(cises[1]);await sleep(350);
        assert.equal(trace.includes('pack:wb-a-order'),false,'must not pack before native receipt');
        assert.equal(trace.includes('lookup:wb-next-order'),false,'next scanner input must wait for held receipt');
        await heldPrint();
      }else if(receiptMode==='lost'){
        for(let i=0;i<70&&!lostAck;i++)await sleep(100);
        assert(lostAck,'fixture must lose native response after accepting job');await sleep(300);
        assert.equal(trace.includes('pack:wb-a-order'),false,'lost accepted response cannot silently pack');
        assert.equal(acceptedPrints.size,1,'one accepted print intent before explicit recovery');
        if(variant==='remount-after-lost-ack'){
          restored=true;
          const saved=await evaluate('JSON.stringify(localStorage)');assert(saved.includes('wb-a-order'),'unfinished order intent must persist before remount');
          await cdp.send('Page.navigate',{url:url+'&preserve=1'});
          await until(`document.querySelector('[data-order-id="wb-a-order"]')&&document.querySelector('[data-testid="fbs-unified-scan"]')`);
        }
        await scan(qrCodes[0]);
        for(let i=0;i<70&&!trace.includes('pack:wb-a-order');i++)await sleep(100);
        assert(trace.includes('pack:wb-a-order'),'same QR must recover original order after uncertain receipt');
        assert.deepEqual(printLog.map(j=>j.idempotencyKey),['scan-wb-a-order','scan-wb-a-order'],'retry must reconcile same accepted print key');
        await scan(qrCodes[1]);await scan(cises[1]);
      }else{await scan(qrCodes[1]);await scan(cises[1]);}
      for(let i=0;i<100&&!trace.includes('pack:wb-next-order');i++)await sleep(100);
      assert(trace.includes('pack:wb-next-order'),`next order did not finish: ${trace.join(' -> ')}`);
      const selections=requestLog.filter(r=>r.path.endsWith('/scan-auto-print')&&r.body?.order_id);
      assert.deepEqual(selections.map(r=>r.body.order_id),server?
        (variant==='remount-after-lost-ack'?['wb-a-order','wb-a-order','wb-next-order']:['wb-a-order','wb-next-order']):[]);
      if(variant==='remount-after-lost-ack'){
        const resumed=selections.filter(r=>r.body.order_id==='wb-a-order');
        assert.equal(resumed.length,2,'one initial and one restored explicit selection');
        assert(resumed.every(r=>typeof r.body.idempotency_key==='string'&&r.body.idempotency_key.trim().length>0),
          'initial/restored explicit selection keys must be nonempty');
        assert.equal(resumed[1].body.idempotency_key,resumed[0].body.idempotency_key,
          'restored explicit selection must reuse initial idempotency key');
        assert.deepEqual(resumed.map(r=>[r.path,r.body.order_id,r.body.barcode]),[
          ['/operations/fbs-supplies/wb-a/scan-auto-print','wb-a-order',qrCodes[0]],
          ['/operations/fbs-supplies/wb-a/scan-auto-print','wb-a-order',qrCodes[0]],
        ],'restored selection must preserve actual supply/order/sticker identity');
      }
      assert(selections.every(r=>r.body.print_chz===false),'explicit sticker may never allocate pool CIS');
      assert(selections.every(r=>r.body.await_honest_sign===true));
      const commits=requestLog.filter(r=>r.path==='/operations/fbs-orders/kiz/commit');
      assert.deepEqual(commits.map(r=>r.body.pairs),['wb-a-order','wb-next-order'].map((id,i)=>[
        {order_id:id,value:cises[i],confirmed:false,...server?{scan_auto_print_id:`scan-${id}`}:{}}]));
      assert(commits.every(r=>r.body.scan_no_wb_wait===true));
      const expectedKeys=['wb-a-order','wb-next-order'].flatMap(id=>[
        ...qr?[`scan-${id}`]:[],...copy?[`scan-${id}:copy`,`scan-${id}:copy:c2`]:[]]);
      assert.deepEqual([...acceptedPrints.keys()],expectedKeys,'exact flags print intents/count; pool is never issued for explicit QR');
      const jobs=[...acceptedPrints.values()].map(x=>x.job);
      assert.deepEqual(jobs.map(p=>[p.widthMm,p.heightMm]),Array(jobs.length).fill([60,80]));
      for(let i=0;i<2;i++){
        if(qr)assert.equal(acceptedPrints.get(`scan-${['wb-a-order','wb-next-order'][i]}`).job.imageDataUrl,`data:image/png;base64,${qrImages[i].toString('base64')}`);
        if(copy){const id=['wb-a-order','wb-next-order'][i];for(const key of [`scan-${id}:copy`,`scan-${id}:copy:c2`])assert.equal(decodedCis(acceptedPrints.get(key).job),cises[i],'native copies encode full canonical CIS per order');assert.equal(acceptedPrints.get(`scan-${id}:copy`).job.imageDataUrl,acceptedPrints.get(`scan-${id}:copy:c2`).job.imageDataUrl);}
      }
      const packs=requestLog.filter(r=>r.path.endsWith('/pack'));
      assert.deepEqual(packs.map(r=>[r.path,r.body.quantity,r.body.order_id]),[
        ['/operations/packaging-tasks/task-wb-a/lines/line-wb-a-order/pack',1,'wb-a-order'],
        [`/operations/packaging-tasks/task-${many?'wb-b':'wb-a'}/lines/line-wb-next-order/pack`,1,'wb-next-order']]);
      for(const pack of packs)assert(server?pack.body.idempotency_key===`scan-${pack.body.order_id}:packed`:/^local:.+:packed$/.test(pack.body.idempotency_key));
      if(qr)assert(trace.indexOf('print:scan-wb-a-order')<trace.indexOf('pack:wb-a-order'));
      assert(trace.indexOf('pack:wb-a-order')<trace.indexOf('lookup:wb-next-order'),'next correct order after first pack');
      assert.equal(blocked.length,0);assert.equal(errors.length,0);
      report.cases.push({id:report.currentCase,status:'PASS'});console.log(`${report.currentCase}: PASS`);
    }catch(e){report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});console.error(`${report.currentCase}: ${e}`);}
    await writeFile(`${dir}/${report.currentCase.replaceAll(/[^a-zA-Z0-9_-]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors,acceptedPrintKeys:[...acceptedPrints.keys()]},null,2));
  }
}

function resetGeometry(){requestLog=[];printLog=[];trace=[];blocked=[];errors=[];heldLookup=undefined;holdFirst=false;heldPrint=undefined;acceptedPrints=new Map();boundOrders=new Map();restored=false;lostAck=false;receiptMode='';}
