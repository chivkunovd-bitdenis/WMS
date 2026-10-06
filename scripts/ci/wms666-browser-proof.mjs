// Runner-only CDP probe. No Playwright, browser library, live API, or printer.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
const BASE = '9a73432accdd5c2ef7b48d08cc8abdef5942c258';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw Error('GitHub Linux runner only');
const dir = process.env.WMS666_EVIDENCE;
await mkdir(dir, { recursive: true });
const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const ts = require('typescript');
const bwip = require('bwip-js');
const { PNG } = require('pngjs');
const source = await readFile('frontend/src/screens/v2/FfFbsUnifiedPacking.wms666.dom.test.tsx', 'utf8');
// Reuse frozen data builders read-only; never import/run or alter DOM tests.
const builders = source.slice(source.indexOf('function order('), source.indexOf('\nfunction packagingTask('));
const js = ts.transpileModule(builders, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText;
const workspace = new Function('WB_BARCODE', 'OZON_POSITION_BARCODE', `${js}; return workspace` )('4606660000001', 'OZON-POS-666-A');
const OZ = '9b3993c3-dffd-5f14-b7b0-2ccf0f495b57';
const state = Object.fromEntries([[OZ, 'ozon'], ['ozon-b', 'ozon'], ['wb-a', 'wb'], ['wb-b', 'wb']].map(([id, mp]) => [id, workspace(id, mp)]));
for (const [id, w] of Object.entries(state)) {
  w.supply.seller.name = `Синтетический селлер ${id} с очень длинным названием для проверки читаемости`;
  w.orders[0].seller.name = w.supply.seller.name;
  w.orders[0].product.name += ' — длинное название товара, коллекция осень, комплект повседневной одежды с подробным описанием';
  for (const p of w.orders[0].positions) p.name += ' — длинное название позиции, коллекция осень, размер и цвет';
}
const initialState = JSON.stringify(state);
const qrPng = await bwip.toBuffer({ bcid: 'qrcode', text: '666001 0001', scale: 3 });
let requestLog = [], printLog = [], blocked = [], errors = [], cdp, sequence = 0;
const report = { base: BASE, probe: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), cases: [], physicalPaper: 'OPEN', staging: 'NOT TESTED', scope: 'Real FBS screen/URL effects, synthetic API; no application shell or live data' };
class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.next = 0; this.pending = new Map(); this.listeners = new Map();
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.id) { const p = this.pending.get(msg.id); this.pending.delete(msg.id); if (p) { clearTimeout(p.timer); msg.error ? p.reject(Error(JSON.stringify(msg.error))) : p.resolve(msg.result); } }
      else for (const f of this.listeners.get(msg.method) ?? []) Promise.resolve(f(msg.params)).catch(e => errors.push(String(e)));
    };
  }
  async send(method, params = {}) {
    await this.ready; const id = ++this.next;
    return new Promise((resolve, reject) => { const timer = setTimeout(() => { this.pending.delete(id); reject(Error(`CDP timeout ${method}`)); }, 12000); this.pending.set(id, { resolve, reject, timer }); this.ws.send(JSON.stringify({ id, method, params })); });
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
async function intercept({ requestId, request }) {
  const u = new URL(request.url), path = u.pathname.replace(/^\/api/, '');
  if (u.origin === 'http://127.0.0.1:16666' && !u.pathname.startsWith('/api/') && path !== '/assets/wms666-wb.png') return cdp.send('Fetch.continueRequest', { requestId });
  if (u.origin === 'http://127.0.0.1:17843' && path === '/print') {
    if (request.method === 'OPTIONS') return fulfill(requestId, {});
    const payload = JSON.parse(request.postData); printLog.push(payload);
    return fulfill(requestId, { receipt: `synthetic-receipt-${printLog.length}` });
  }
  if (u.origin !== 'http://127.0.0.1:16666') { blocked.push(request.url); return cdp.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }); }
  const body = request.postData ? JSON.parse(request.postData) : null;
  requestLog.push({ method: request.method, path: path + u.search, body });
  if (path === '/assets/wms666-wb.png') return fulfill(requestId, qrPng, 200, 'image/png');
  const ws = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/(workspace|start-work)$/);
  if (ws && state[ws[1]]) return fulfill(requestId, state[ws[1]]);
  const task = path.match(/^\/operations\/packaging-tasks\/task-([^/]+)$/);
  if (task && state[task[1]]) {
    const w = state[task[1]];
    return fulfill(requestId, { id: w.supply.packaging_task_id, status: 'in_progress', lines: w.orders.flatMap(o => (o.positions.length ? o.positions : [o.product]).map((p, i) => ({ id: `${task[1]}-line-${i}`, product_id: p.product_id ?? p.id, product_name: p.name, sku_code: p.sku, requires_honest_sign: false, packaging_instructions: '', qty_total: 1, qty_need_pack: 1, marking_available_count: 0 }))) });
  }
  if (path.endsWith('/worklist') || path === '/operations/fbs-assembly-tasks') return fulfill(requestId, { items: [], total: 0, warehouse_options: [], server_now: '2026-10-06T08:00:00Z' });
  if (path === '/auth/me') return fulfill(requestId, {separate_marking_print_enabled:false});
  if (path.endsWith('/order-print-tape')) return fulfill(requestId, {orders:[],order_errors:[],shortage:0});
  if (path === '/fbs/assembly-time') return fulfill(requestId, { hours: 0, orders: 0, in12: null, in24: null });
  const scan = path.match(/^\/operations\/fbs-supplies\/(wb-[ab])\/scan-auto-print$/);
  if (scan) {
    if (body?.barcode !== '4606660000001') return fulfill(requestId, {detail:{code:'scan_product_not_found',message:'Товар не найден'}}, 404);
    const o = state[scan[1]].orders[0];
    return fulfill(requestId, { scan_id: `scan-${++sequence}`, order_id: o.id, wb_order_id: o.wb_order_id, replayed: false, binding_target: null, reprint_recovery: null, requires_honest_sign: false, qr_asset: { id: `qr-${o.id}`, kind: 'order_sticker', status: 'ready', content_type: 'image/png', width_mm: 58, height_mm: 40, preview_url: '/assets/wms666-wb.png', download_url: null, checksum: null, applied_at: null, error: null }, codes: [], printed_codes: [], shortage: 0, order_errors: [] });
  }
  if (path.includes('/scan-auto-print/') && path.endsWith('/print-claim')) return fulfill(requestId, { claimed: true, started: false });
  if (path.includes('/scan-auto-print/') && path.endsWith('/print-started')) return fulfill(requestId, { claimed: false, started: true });
  if (path === '/operations/fbs-orders/kiz/lookup') {
    const o = state[u.searchParams.get('supply_id')]?.orders[0];
    if (o?.marketplace === 'ozon' && u.searchParams.get('sticker') === o.external_order_id) return fulfill(requestId, { order_id: o.id, wb_order_id: o.wb_order_id, product: { name: o.product.name, image_url: null, barcode: o.product.barcode, seller_article: o.product.seller_article }, current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null, requires_honest_sign: false });
    return fulfill(requestId, { detail: { code: 'sticker_not_found', message: 'Стикер не найден' } }, 404);
  }
  const assign = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/boxes\/([^/]+)\/orders$/);
  if (assign) { const w = state[assign[1]], b = w.boxes[0]; b.assigned_order_ids = body.order_ids.length ? body.order_ids : [w.orders[0].id]; b.assigned_order_product_ids = body.order_product_ids ?? []; return fulfill(requestId, w); }
  return fulfill(requestId, { detail: { code: 'unhandled_synthetic_endpoint', message: path } }, 404);
}
async function capture(name) {
  const png = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  await writeFile(`${dir}/${name}.png`, Buffer.from(png.data, 'base64'));
  await writeFile(`${dir}/${name}.ax.json`, JSON.stringify(await cdp.send('Accessibility.getFullAXTree'), null, 2));
  await writeFile(`${dir}/${name}.html`, await evaluate('document.documentElement.outerHTML'));
}
async function scan(code) {
  await evaluate(`document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]')?.focus()`);
  await cdp.send('Input.insertText', { text: code });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
}
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--disable-component-update', '--remote-debugging-port=16667', `--user-data-dir=${process.env.RUNNER_TEMP}/wms666-chrome-profile`, 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
let chromeLog = ''; chrome.stderr.on('data', d => { chromeLog += d; });
chrome.stdout.on('data', d => { chromeLog += d; });
chrome.on('error', e => { chromeLog += String(e); });
chrome.on('exit', (code, signal) => { chromeLog += `\nChrome exit code=${code} signal=${signal}\n`; });
try {
  let tabs;
  for (let i = 0; i < 200; i++) { try { tabs = await (await fetch('http://127.0.0.1:16667/json/list')).json(); break; } catch { await sleep(100); } }
  assert(tabs?.length, `Chromium did not start: ${chromeLog}`);
  cdp = new CDP(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
  cdp.on('Fetch.requestPaused', intercept);
  cdp.on('Runtime.exceptionThrown', e => errors.push(e.exceptionDetails));
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Accessibility.enable');
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', JSON.stringify({printQr:true,printChz:true,reprintChz:false,printChzCopies:2}));
    localStorage.setItem('wms.print.labelSizeId','60x80');
    const p = new URLSearchParams(location.search), ids = (p.get('supply_ids')||p.get('supply_id')||'').split(',');
    sessionStorage.setItem('wms:fbs:assembly:'+ids.join(',')+':stage','packing');
    ids.forEach(id=>sessionStorage.setItem('wms:fbs:'+id+':stage','packing'));
  ` });
  report.browser = await cdp.send('Browser.getVersion');
  const cases = [['ozon-single', `supply_id=${OZ}`, [OZ]], ['ozon-group-one', `supply_ids=${OZ}`, [OZ]], ['ozon-group-many', `supply_ids=${OZ},ozon-b`, [OZ,'ozon-b']], ['multi-wb', 'supply_ids=wb-a,wb-b', ['wb-a','wb-b']], ['mixed', `supply_ids=wb-a,${OZ}`, ['wb-a',OZ]]];
  for (const [name, query, ids] of cases) {
    Object.assign(state, JSON.parse(initialState));
    report.currentCase = name;
    requestLog = []; printLog = []; blocked = []; errors = [];
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:16666/app/ff/fbs?${query}` });
    await until(`document.querySelectorAll('[data-order-id]').length===${ids.length} && document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')`);
    await evaluate('document.fonts.ready.then(()=>true)'); await sleep(350);
    const geometry = await evaluate(`(() => {
      const bar=document.querySelector('[data-testid="fbs-unified-scan"]');
      const qr=bar.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input');
      const bounds=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
      const rows=[...document.querySelectorAll('[data-order-id]')];
      const controls=[...bar.querySelectorAll('button,input')].filter(e=>e.getBoundingClientRect().width>0);
      const overlap=(a,b)=>a.x<b.right-1&&b.x<a.right-1&&a.y<b.bottom-1&&b.y<a.bottom-1;
      return {url:location.href,bars:document.querySelectorAll('[data-testid="fbs-unified-scan"]').length, lists:document.querySelectorAll('[data-testid="fbs-unified-packing-rows"]').length,oldButtons:/Начать работу с поставкой|Завершить работу с поставкой/.test(document.body.innerText),activeFrames:document.querySelectorAll('[data-active]').length,qr:{checked:qr.checked,disabled:qr.disabled,color:getComputedStyle(qr.closest('label')).color,checkboxColor:getComputedStyle(qr.parentElement).color},settings:bar.innerText,bar:bounds(bar),controls:controls.map(e=>({tag:e.tagName,label:e.getAttribute('aria-label'),bounds:bounds(e)})),controlOverlap:controls.some((e,i)=>controls.slice(i+1).some(f=>overlap(bounds(e),bounds(f)))),rows:rows.map(e=>({id:e.dataset.orderId,text:e.innerText,bounds:bounds(e),actions:[...e.querySelectorAll('button')].map(b=>({label:b.getAttribute('aria-label')||b.innerText,bounds:bounds(b)}))})), rowOverlap:rows.some((e,i)=>rows.slice(i+1).some(f=>overlap(bounds(e),bounds(f))))};
    })()`);
    await writeFile(`${dir}/${name}.geometry.json`, JSON.stringify(geometry, null, 2));
    await capture(name);
    assert.equal(geometry.bars, 1); assert.equal(geometry.lists, 1); assert.equal(geometry.oldButtons, false); assert.equal(geometry.activeFrames, 0);
    assert.equal(geometry.controlOverlap, false, `${name}: scan controls overlap`); assert.equal(geometry.rowOverlap, false);
    assert.equal(geometry.qr.disabled, name.startsWith('ozon')); assert.equal(geometry.qr.checked, !name.startsWith('ozon'));
    const ax = await cdp.send('Accessibility.getFullAXTree');
    const qrAX = ax.nodes.find(n=>n.role?.value==='checkbox' && n.name?.value==='Печатать QR');
    assert(qrAX, `${name}: QR accessible name missing`);
    assert.equal(qrAX.properties.some(p=>p.name==='disabled'&&p.value.value===true), name.startsWith('ozon'));
    if (name.startsWith('ozon')) {
      await evaluate(`document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input').click()`);
      assert.equal(await evaluate(`document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input').checked`), false);
      await scan('OZON-POS-666-A');
      await until(`!document.querySelector('[data-testid="fbs-kiz-scan-active"]')`, 4000);
      await sleep(500);
      assert(requestLog.some(r=>r.path.includes('/kiz/lookup')&&r.path.includes(OZ)), 'Ozon scan lookup missing');
      // The standalone card has no group open-box context; box assignment is a group assertion.
      if (name !== 'ozon-single') assert(requestLog.some(r=>r.path.includes('/boxes/')&&r.body?.order_product_ids?.includes(`${OZ}-position-a`)), 'Ozon position did not reach its group box');
      assert.equal(printLog.length, 0, 'Ozon scan emitted native QR print');
      assert.equal(requestLog.filter(r=>r.path.includes('/scan-auto-print')).length, 0);
    }
    if (name === 'mixed') {
      await scan('4606660000001');
      for(let i=0;i<60&&!printLog.length;i++) await sleep(100);
      assert.equal(printLog.length,1,'WB scan native print payload missing');
      const p=printLog[0]; assert.equal(p.widthMm,60); assert.equal(p.heightMm,80); assert(p.idempotencyKey); assert(p.imageDataUrl.startsWith('data:image/png;base64,'));
      const bytes=Buffer.from(p.imageDataUrl.split(',')[1],'base64'); const image=PNG.sync.read(bytes);
      await writeFile(`${dir}/mixed-wb-qr-payload.png`,bytes);
      report.qrPayload={widthMm:p.widthMm,heightMm:p.heightMm,pixelWidth:image.width,pixelHeight:image.height,sha256:createHash('sha256').update(bytes).digest('hex'),idempotencyKey:p.idempotencyKey};
      await scan('OZON-POS-666-A'); await sleep(700);
      assert(requestLog.some(r=>r.path.includes(`/fbs-supplies/${OZ}/boxes/`)&&r.body?.order_product_ids?.includes(`${OZ}-position-a`)));
      assert.equal(printLog.length,1,'Mixed Ozon emitted QR print');
      await capture('mixed-after-scans');
    }
    if (name.startsWith('ozon') || name === 'mixed') {
      const rowId = `${OZ}-order`;
      for (const [action, expr] of [['row', `document.querySelector('[data-order-id="${rowId}"] button[aria-label="Печать ЧЗ и ШК"]')`], ['bulk', `[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith('Печать всего ('))`]]) {
        // Mixed bulk belongs to both marketplaces; select only the Ozon row first.
        if (name === 'mixed' && action === 'bulk') {
          await evaluate(`document.querySelector('[data-order-id="${rowId}"] input[type="checkbox"]').click()`);
        }
        const selector = name === 'mixed' && action === 'bulk'
          ? `[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith('Печать выбранного ('))` : expr;
        await evaluate(`(${selector}).click()`);
        await until(`document.querySelector('[data-testid="marking-print-confirm"]')`);
        await capture(`${name}-${action}-print`);
        const before = requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length;
        await evaluate(`document.querySelector('[data-testid="marking-print-confirm"]').click()`);
        for(let i=0;i<50 && requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length===before;i++) await sleep(100);
        const intent=requestLog.filter(r=>r.path.endsWith('/order-print-tape')).at(-1);
        assert.equal(requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length,before+1,`${name} ${action}: print intent missing`);
        assert.equal(intent.body.include_order_qr,false,`${name} ${action}: Ozon QR intent`);
        assert(intent.body.order_ids.every(id=>id.includes(OZ)||id.includes('ozon-b')));
        // Synthetic server returns no printable assets: this proves request intent, not manual paper output.
        await until(`document.querySelector('[data-testid="marking-print-error"]')`);
        await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find(b=>b.textContent==='Отмена').click()`);
        await until(`!document.querySelector('[data-testid="marking-print-confirm"]')`);
        assert.equal(printLog.length,name==='mixed'?1:0,`${name} ${action}: Ozon native QR print`);
      }
    }
    await writeFile(`${dir}/${name}.requests.json`,JSON.stringify({requestLog,printLog,blocked,errors},null,2));
    assert.equal(errors.length,0,`${name}: browser/probe exceptions`);
    report.cases.push({name,url:geometry.url,status:'PASS',rows:geometry.rows.length,qr:geometry.qr,printPayloads:printLog.length});
    console.log(`${name}: PASS`);
  }
  report.status='PASS';
} catch(e) {
  report.status='FAIL'; report.failure=String(e); report.stack=e.stack; console.error(e);
  if(cdp) { try {await capture('failure');}catch{} }
  process.exitCode=1;
} finally {
  await writeFile(`${dir}/last-requests.json`,JSON.stringify({requestLog,printLog,blocked,errors},null,2));
  await writeFile(`${dir}/result.json`,JSON.stringify(report,null,2));
  await writeFile(`${dir}/chrome.log`,chromeLog);
  cdp?.ws.close(); chrome.kill();
}
