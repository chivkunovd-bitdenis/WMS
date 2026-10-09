// WMS652 critical real-screen contracts. No mocked product controllers.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { workspace, selectionFixtures } from '../../../../../frontend/tests-e2e/wms652-critical/fixtures.mjs';
import { createHash } from 'node:crypto';
const require = createRequire(new URL('../../../../../frontend/package.json', import.meta.url));
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
const ORIGIN = 'http://127.0.0.1:16676';
const dir = process.env.WMS652_EVIDENCE;
if (!dir) throw Error('Set WMS652_EVIDENCE to a persistent evidence directory');
await mkdir(dir,{recursive:true});
const qrCodes = ['*DUIkWJJF', '*DUIkNEXT'];
const cises = ['010460000000000121SERIAL-A\u001d91ABCD\u001d92signed-A','010460000000000221SERIAL-B\u001d91EFGH\u001d92signed-B'];
const qrImages = await Promise.all(qrCodes.map(text => bwip.toBuffer({bcid:'qrcode',text,scale:3})));
let requestLog=[],printLog=[],trace=[],blocked=[],errors=[],state,heldLookup,holdFirst;
let receiptMode='', heldPrint, acceptedPrints=new Map(), lostAck=false, boundOrders=new Map(), restored=false;
const markingIds={'wb-a-order':'66600000-0000-4000-8000-000000000001','wb-next-order':'66600000-0000-4000-8000-000000000002'};let keyPrefix=''; let cdp, mode='qr', selectionState, failedGroup, groupAttempts, addAttempts, createdRefs, heldAdd;
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
    const bytes=Buffer.from(job.imageDataUrl.split(',')[1],'base64');
    const response=await fetch(request.url,{method:'POST',headers:{'Content-Type':'application/json','X-WMS-Print':'1',Origin:'https://sellerfocus.pro'},body:request.postData});
    const result=await response.json();assert.equal(response.status,200,JSON.stringify(result));
    acceptedPrints.set(job.idempotencyKey,{job,receipt:result.receipt,png_sha256:createHash('sha256').update(bytes).digest('hex')});
    return fulfill(requestId,result,response.status);
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
  if(path.endsWith('/order-print-tape')){
    const orders=body.order_ids.map(id=>Object.values(state).flatMap(w=>w.orders).find(o=>o.id===id));
    assert(orders.every(o=>o&&path.includes('/'+o.supply_id+'/')),'manual tape may contain only selected orders of its own supply');
    return fulfill(requestId,{orders:orders.map(o=>({order_id:o.id,wb_order_id:o.wb_order_id,requires_honest_sign:true,
      qr_asset:{id:'qr-'+o.id,status:'ready',preview_url:'/assets/qr-'+o.id+'.png',applied_at:'2026-10-09T00:00:00Z'},
      printed_codes:[{id:markingIds[o.id],cis_code:cises[o.id==='wb-a-order'?0:1],has_label_artifact:false,order_product_id:null}],shortage:0})),order_errors:[],shortage:0});
  }
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
    return fulfill(requestId,{scan_id:`${keyPrefix}scan-${one.id}`,order_id:one.id,wb_order_id:one.wb_order_id,
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
  const copy=path.match(/\/scan-auto-print\/[^/]*scan-(.+)\/reprint-claim$/);
  if(copy)return fulfill(requestId,{claimed:true,started:false,kiz:cises[copy[1]==='wb-a-order'?0:1],code_id:null,has_label_artifact:false});
  if(path.endsWith('/print-claim'))return fulfill(requestId,{claimed:true,started:false});
  if(path.endsWith('/print-started'))return fulfill(requestId,{claimed:false,started:true});
  const task=path.match(/^\/operations\/packaging-tasks\/task-([^/]+)$/);
  if(task)return fulfill(requestId,{id:`task-${task[1]}`,document_number:task[1],display_number:task[1],status:'in_progress',
    lines:state[task[1]].orders.map(o=>({id:`line-${o.id}`,product_id:o.product.id,product_name:o.product.name,
      sku_code:o.product.sku,requires_honest_sign:true,packaging_instructions:'',qty_total:1,qty_need_pack:1,marking_available_count:mode==='manual'?4:0}))});
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
 '--remote-debugging-port=16677',`--user-data-dir=${mkdtempSync(`${tmpdir()}/wms652-critical-chrome-`)}`,'about:blank'],{stdio:['ignore','pipe','pipe']});
let chromeLog='';chrome.stderr.on('data',d=>{chromeLog+=d});chrome.stdout.on('data',d=>{chromeLog+=d});chrome.on('error',e=>{chromeLog+=String(e)});
try {
  let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch('http://127.0.0.1:16677/json/list')).json();break}catch{await sleep(100)}}
  assert(tabs?.length,`Chrome unavailable: ${chromeLog}`);
  cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);cdp.on('Fetch.requestPaused',intercept);
  cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
  await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
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
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__WMS_CAPTURE_PRINT_HTML__=true;window.__AUDIT_HTML_PRINTS__=[];window.open=()=>null;window.print=()=>{top.__AUDIT_HTML_PRINTS__.push(document.documentElement.outerHTML)};`});
  await cdp.send('Emulation.setDeviceMetricsOverride' ,{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  for(const [id,query,many] of (process.env.WMS_NATIVE_SKIP_SCANS==='1'?[]:[['supply_id=A','supply_id=wb-a',false],['supply_ids=A,B','supply_ids=wb-a,wb-b',true]])){
    try {
    prepareState(many);requestLog=[];printLog=[];trace=[];blocked=[];errors=[];heldLookup=undefined;holdFirst=true;
    report.currentCase=`WMS666.native.consecutive[${id}]`;keyPrefix=id.replaceAll(/[^A-Za-z0-9]/g,'')+':';
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
      [{order_id:'wb-a-order',value:cises[0],confirmed:false,scan_auto_print_id:`${keyPrefix}scan-wb-a-order`}],
      [{order_id:'wb-next-order',value:cises[1],confirmed:false,scan_auto_print_id:`${keyPrefix}scan-wb-next-order`}],
    ]);
    assert(commits.every(r=>r.body.scan_no_wb_wait===true));
    assert.deepEqual(printLog.map(p=>p.idempotencyKey),[`${keyPrefix}scan-wb-a-order`,`${keyPrefix}scan-wb-a-order:copy`,`${keyPrefix}scan-wb-a-order:copy:c2`,
      `${keyPrefix}scan-wb-next-order`,`${keyPrefix}scan-wb-next-order:copy`,`${keyPrefix}scan-wb-next-order:copy:c2`]);
    assert.deepEqual(printLog.map(p=>[p.widthMm,p.heightMm]),Array(6).fill([60,80]));
    assert.equal(printLog[0].imageDataUrl,`data:image/png;base64,${qrImages[0].toString('base64')}`);
    assert.equal(printLog[3].imageDataUrl,`data:image/png;base64,${qrImages[1].toString('base64')}`);
    for(const [index,cis] of [[1,cises[0]],[2,cises[0]],[4,cises[1]],[5,cises[1]]])assert.equal(decodedCis(printLog[index]),cis,'native copy must encode full canonical CIS of this order');
    assert.equal(printLog[1].imageDataUrl,printLog[2].imageDataUrl);assert.equal(printLog[4].imageDataUrl,printLog[5].imageDataUrl);
    assert.notEqual(printLog[1].imageDataUrl,printLog[4].imageDataUrl,'different canonical CIS must yield different exact copies');
    for(const index of [1,4]){const image=PNG.sync.read(Buffer.from(printLog[index].imageDataUrl.split(',')[1],'base64'));assert.equal(image.width,720);assert.equal(image.height,960);}
    const packs=requestLog.filter(r=>r.path.endsWith('/pack'));
    assert.deepEqual(packs.map(r=>r.body),[{quantity:1,order_id:'wb-a-order',idempotency_key:`${keyPrefix}scan-wb-a-order:packed`},
      {quantity:1,order_id:'wb-next-order',idempotency_key:`${keyPrefix}scan-wb-next-order:packed`}]);
    assert.deepEqual(packs.map(r=>r.path),['/operations/packaging-tasks/task-wb-a/lines/line-wb-a-order/pack',
      `/operations/packaging-tasks/task-${many?'wb-b':'wb-a'}/lines/line-wb-next-order/pack`]);
    assert.deepEqual(trace.filter(x=>x.startsWith('product-miss:')),qrCodes.map(q=>`product-miss:${q}`));
    assert(trace.indexOf(`print:${keyPrefix}scan-wb-a-order`)<trace.indexOf('pack:wb-a-order'));
    assert(trace.indexOf('pack:wb-a-order')<trace.indexOf('lookup:wb-next-order'));
    assert(trace.indexOf(`print:${keyPrefix}scan-wb-next-order:copy:c2`)<trace.indexOf('pack:wb-next-order'));
    assert.equal(blocked.length,0);assert.equal(errors.length,0);
    await writeFile(`${dir}/${id.replaceAll(/[=,]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
    report.cases.push({id:report.currentCase,status:'PASS'});console.log(`${report.currentCase}: PASS`);
    } catch(e) {
      await writeFile(`${dir}/${id.replaceAll(/[=,]/g,'-')}.failure-ui.txt`,await evaluate('document.body.innerText'));
      report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});
      await writeFile(`${dir}/${id.replaceAll(/[=,]/g,'-')}.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
      console.error(`${report.currentCase}: ${e}`);
    }
  }
  await manualContracts();
  assert(report.cases.every(one=>one.status==='PASS'),'one or more targeted print cases failed');
  report.status='PASS';
}catch(e){if(report.currentCase&&!report.cases.some(one=>one.id===report.currentCase))report.cases.push({id:report.currentCase,status:'FAIL',failure:String(e)});report.status='FAIL';report.failure=String(e);report.stack=e.stack;console.error(e);process.exitCode=1;}
finally{
  await writeFile(`${dir}/cdp-transport.json`,JSON.stringify({events:cdp?.transport ?? [],pendingCommandIds:[...cdp?.pending.keys() ?? []]},null,2));
  await writeFile(`${dir}/result.json`,JSON.stringify(report,null,2));
  await writeFile(`${dir}/last-requests.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
  await writeFile(`${dir}/chrome.log`,chromeLog);cdp?.ws.close();chrome.kill();
}

async function click(id){await evaluate(`document.querySelector('[data-testid="${id}"]').click()`);}
async function manualContracts(){
  for(const [name,query,many] of [['ordinary','supply_id=wb-a',false],['group','supply_ids=wb-a,wb-b',true]]){
    mode='manual';prepareState(many);requestLog=[];printLog=[];trace=[];blocked=[];errors=[];holdFirst=false;
    for(const w of Object.values(state))for(const o of w.orders){o.product.requires_honest_sign=true;o.marking_available_count=4;}
    report.currentCase=`WMS666.manual.selected.${name}`;
    await cdp.send('Page.navigate',{url:`${ORIGIN}/app/ff/fbs?${query}`});
    await until(`document.querySelectorAll('[data-order-id]').length===2&&document.querySelector('[data-testid="fbs-packing-print"]')`);
    await evaluate(`window.__AUDIT_HTML_PRINTS__=[];window.__WMS_CAPTURE_PRINT_HTML__=true;window.open=()=>null;`);
    const select=id=>evaluate(`document.querySelector('[data-order-id="${id}"] [data-testid="fbs-packing-select-order"] input').click()`);
    await select('wb-a-order');if(many)await select('wb-next-order');
    await until(`document.querySelector('[data-testid="fbs-packing-print"]').textContent.includes('(${many?2:1})')`);
    await click('fbs-packing-print');
    await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);
    await click('marking-print-confirm');
    await until(`window.__AUDIT_HTML_PRINTS__.length>=1`);
    if(many){await until(`document.querySelector('[data-testid="marking-print-confirm"]')&&!document.querySelector('[data-testid="marking-print-confirm"]').disabled`);await click('marking-print-confirm');await until(`window.__AUDIT_HTML_PRINTS__.length===2`);}
    await until(`!document.querySelector('[data-testid="marking-print-confirm"]')`);
    const tapes=requestLog.filter(r=>r.path.endsWith('/order-print-tape'));
    assert.deepEqual(tapes.map(r=>r.body.order_ids),many?[['wb-a-order'],['wb-next-order']]:[['wb-a-order']]);
    const html=await evaluate('window.__AUDIT_HTML_PRINTS__');
    await writeFile(`${dir}/${name}-manual-html.json`,JSON.stringify(html,null,2));
    await writeFile(`${dir}/${name}-manual.json`,JSON.stringify({requestLog,printLog,trace,blocked,errors},null,2));
    assert.equal(printLog.length,0,'manual tape uses browser HTML path, not Direct Handler');
    assert.equal(errors.length,0);assert.equal(blocked.length,0);
    report.cases.push({id:report.currentCase,status:'PASS',boundary:'browser HTML/window.print',scopedOrders:tapes.map(r=>r.body.order_ids),htmlPrints:html.length});
    console.log(report.currentCase+': PASS');
    if(many){
      report.currentCase='WMS666.manual.cancel-stops-group';requestLog=[];
      await click('fbs-packing-print');await until(`document.querySelector('[data-testid="marking-print-confirm"]')`);
      await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find(b=>b.textContent==='Отмена').click()`);
      await until(`!document.querySelector('[data-testid="marking-print-confirm"]')`);await sleep(500);
      assert.equal(requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length,0,'cancel prevents first tape and remaining group');
      assert.equal(await evaluate('window.__AUDIT_HTML_PRINTS__.length'),2,'cancel creates no new print');
      assert.equal(await evaluate('document.querySelector("[data-testid=fbs-packing-print]").disabled'),false);
      await writeFile(`${dir}/group-cancel.json`,JSON.stringify({requestLog,htmlPrints:2},null,2));
      report.cases.push({id:report.currentCase,status:'PASS',tapeRequestsAfterCancel:0,newPrintsAfterCancel:0});console.log(report.currentCase+': PASS');
    }
  }
}
