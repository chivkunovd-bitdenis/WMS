// TESTER672 only: new narrow probes; original frozen contracts remain untouched.
import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw new Error('Remote Linux runner only');
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const base = process.env.WMS672_TEST_URL;
const evidence = process.env.WMS672_EVIDENCE_DIR;
let browser;
before(async () => { await mkdir(evidence,{recursive:true}); browser=await chromium.launch({headless:true,executablePath:process.env.WMS672_CHROMIUM}); });
after(async () => browser?.close());
function detail(n, operation = 'inbound') {
  return {
    id: '672-document', warehouse_id: '672-warehouse', seller_id: '672-seller',
    seller_name: 'Синтетический селлер с очень длинным названием организации для проверки читаемости элементов и соседних действий', document_number: '672 — длинное название документа для проверки размещения действий', display_number: '672 — длинное название документа для проверки размещения действий',
    status: 'receiving', operation_type: operation, marketplace: 'wildberries',
    planned_box_count: n, actual_box_count: n, lines: [], cargo_places: [],
    boxes: Array.from({ length: n }, (_, i) => ({
      id: `672-box-${i + 1}`, box_number: i + 1,
      internal_barcode: `INB-${String(i + 1).padStart(12, '0')}`,
      label_printed_at: null, intake_opened_at: null, intake_closed_at: null,
      is_open: false, lines: [],
    })),
  };
}

async function fixture(n, operation = 'inbound', fault = {}) {
  const context = await browser.newContext({ viewport: {width: 1440, height: 1050}, deviceScaleFactor: 1 });
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = new Set();
  page.on('pageerror', e => { if (!errors.has(e.message)) { errors.add(e.message); console.error('WMS672 browser error:', e.stack); } });
  const data = detail(n, operation);
  const original = structuredClone(data);
  const calls = [];
  let marks = 0;
  const successfulMarks = [];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    calls.push({ path, method, body: request.postData(), headers: request.headers() });
    if (path.endsWith('/mark-label-printed')) {
      marks += 1;
      if (fault.markAt === marks) {
        // The server accepted the mark, but its response is lost.
        await page.waitForFunction(() => window.__wms672Transfers.length === 1);
        return route.abort('failed');
      }
      successfulMarks.push({ path, transfers: await page.evaluate(() => window.__wms672Transfers.length) });
      return route.fulfill({ json: {} });
    }
    if (method !== 'GET') return route.fulfill({ status: 409, json: { detail: 'unexpected_mutation' } });
    if (path.endsWith('/inbound-intake-requests/672-document')) return route.fulfill({ json: data });
    if (path.endsWith('/marking-codes')) return route.fulfill({ json: { items: [], checking: false } });
    return route.fulfill({ json: [] });
  });
  await page.goto(`${base}/tests-e2e/wms672-harness.html`);
  await install(page, fault);
  await page.getByTestId('ff-inbound-packages-toggle').click();
  await page.getByTestId('ff-inbound-boxes-print-all').waitFor();
  return { page, context, data, original, calls, marks: () => marks, successfulMarks };
}

async function confirm(f, action = 'ff-inbound-boxes-print-all') {
  await f.page.getByTestId(action).click();
  await f.page.getByTestId('ff-inbound-box-print-dialog-confirm').click();
}
async function transfer(f, count = 1, polling = 'raf') {
  await f.page.waitForFunction(n => window.__wms672Transfers.length >= n, count, { polling });
  return f.page.evaluate(() => window.__wms672Transfers);
}

async function install(page, fault = {}) {
  await page.evaluate(async ({ fault }) => {
    window.__WMS_CAPTURE_PRINT_HTML__ = true;
    window.__wms672Transfers = [];
    window.__wms672Decoded = 0;
    window.__wms672DecodeStarted = 0;
    window.__wms672DecodeEvents = [];
    window.__wms672Frames = 0;
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = callback => fault.stallFrames ? 0 : raf(time => {
      window.__wms672Frames += 1; callback(time);
    });
    window.__wms672Fault = fault;
    window.__wms672Hold = Boolean(fault.hold);
    // Each srcdoc navigation has its own prototypes. Install before the real onload handler.
    const append = document.body.appendChild.bind(document.body);
    document.body.appendChild = function (node) {
      const result = append(node);
      if (node.tagName === 'IFRAME') node.addEventListener('load', () => {
        const w = node.contentWindow;
        const decode = w.HTMLImageElement.prototype.decode;
        let ready = 0; // successful native decodes in this exact source frame
        w.HTMLImageElement.prototype.decode = async function () {
          if (!this.classList.contains('barcode')) return decode.call(this);
          const index = ++window.__wms672DecodeStarted;
          window.__wms672DecodeEvents.push({ index, frame: window.__wms672Frames });
          if (window.__wms672Fault.decodeAt === index) throw new Error(`WMS672 decode failed at ${index}`);
          while (window.__wms672Hold) await new Promise(r => setTimeout(r, 10));
          if (fault.delayMs) await new Promise(r => setTimeout(r, fault.delayMs));
          await decode.call(this);
          ready += 1;
          window.__wms672Decoded += 1;
        };
        w.focus = () => {};
        w.print = () => {
          window.__wms672Transfers.push({ html: node.srcdoc, decoded: ready,
            attempt: Object.values(localStorage).map(value => { try { return JSON.parse(value)?.labelAttempt; } catch { return null; } }).find(Boolean) });
          if (window.__wms672Fault.unknown) throw new Error('Synthetic lost transfer acknowledgement');
        };
      });
      return result;
    };
    const { mountInbound672 } = await import('/tests-e2e/wms672-harness.tsx');
    window.__wms672Root = mountInbound672(document.getElementById('root'));
  }, { fault });
}

async function capture(f, name) {
  // Finish real MUI transitions before taking visual evidence; do not alter UI.
  await f.page.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));await Promise.allSettled(document.getAnimations().map(a=>a.finished));});
  await f.page.screenshot({path: resolve(evidence, name+'.png'), fullPage:true});
  await writeFile(resolve(evidence,name+'.json'),JSON.stringify({calls:f.calls, state:await f.page.evaluate(()=>({local:Object.entries(localStorage), alerts:[...document.querySelectorAll('[role=alert]')].map(a=>a.textContent), transfers:window.__wms672Transfers?.length}))},null,2));
}
async function attempt(page) { return page.evaluate(()=>Object.values(localStorage).map(x=>{try{return JSON.parse(x).labelAttempt}catch{return null}}).find(Boolean)); }
for (const operation of ['inbound','return']) {
 test(`C7 remaining ${operation}: unknown reload, operator clarification then distinct explicit reprint`,async()=>{
  const f=await fixture(3,operation,{unknown:true});
  try {
   await confirm(f); await f.page.getByRole('alert').waitFor();
   const old=await attempt(f.page); assert.equal(old.state,'unknown'); assert.equal(old.html, undefined, 'WMS-743: no label HTML in storage'); assert.equal(old.paths.length, 3, 'the attempt still identifies its boxes');
   assert.equal(f.marks(),0); assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),1);
   await capture(f,operation+'-unknown');
   await f.page.reload(); await install(f.page,{});
   await f.page.getByTestId('ff-inbound-packages-toggle').click();
   assert.equal((await attempt(f.page)).id,old.id);
   assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),0);
   const dialogs=[]; let accept=false;
   f.page.on('dialog',async d=>{dialogs.push({message:d.message(),accept,reads:f.calls.filter(c=>c.method==='GET').length}); await (accept?d.accept():d.dismiss());});
   let reads=f.calls.filter(c=>c.method==='GET').length;
   await confirm(f); await f.page.getByRole('alert').waitFor();
   assert.equal(dialogs.length,1); assert.match(dialogs[0].message,/Результат проверен/);
   assert.ok(dialogs[0].reads>reads,'document reread before operator clarification');
   assert.equal((await attempt(f.page)).state,'unknown'); assert.equal(f.marks(),0);
   assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),0);
   accept=true; await confirm(f); await f.page.getByRole('alert').waitFor();
   await f.page.waitForFunction(()=>Object.values(localStorage).some(x=>{try{return JSON.parse(x).labelAttempt?.state==='complete'}catch{return false}}));
   assert.equal((await attempt(f.page)).id,old.id); assert.equal(f.marks(),0);
   assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),0,'clarification is not reprint');
   await confirm(f); await transfer(f);
   await f.page.waitForFunction(()=>Object.values(localStorage).some(x=>{try{return JSON.parse(x).labelAttempt?.state==='complete' && JSON.parse(x).labelAttempt.paths.length===0}catch{return false}}));
   const fresh=await attempt(f.page); assert.notEqual(fresh.id,old.id); assert.equal(f.marks(),3);
   assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),1);
   await writeFile(resolve(evidence,operation+'-clarification.json'),JSON.stringify({oldId:old.id,newId:fresh.id,dialogs,totalInterceptedTransfers:2,marks:f.marks()},null,2));
   await capture(f,operation+'-explicit-reprint');
  } finally {await f.context.close();}
 });
 test(`C11 ${operation}: actual placement dialog long names preview error and neighbors`,async()=>{
  const f=await fixture(3,operation,{decodeAt:2});
  try {
   const controls=['ff-inbound-add-to-box','ff-inbound-create-cargo-places','ff-inbound-boxes-print-all','ff-inbound-cargo-places-print-all'];
   const layout=await f.page.evaluate(ids=>ids.map(id=>{const e=document.querySelector(`[data-testid="${id}"]`);const r=e.getBoundingClientRect();return {id,text:e.textContent,x:r.x,y:r.y,width:r.width,height:r.height,parent:e.parentElement.innerHTML};}),controls);
   assert.ok(layout.every(x=>x.width>0)); assert.ok(layout.every(x=>x.parent===layout[0].parent),'existing package action group');
   assert.ok(layout[2].x>=layout[1].x+layout[1].width-1,'print follows cargo creation');
   await capture(f,operation+'-screen');
   await f.page.getByTestId('ff-inbound-boxes-print-all').click();
   const dialog=f.page.getByTestId('ff-inbound-box-print-dialog');
   await dialog.getByTestId('ff-inbound-box-print-dialog-confirm').waitFor();
   assert.match(await dialog.innerText(),/58.*40/s);
   await capture(f,operation+'-dialog');
   await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   assert.equal(f.marks(),0);
   await f.page.getByTestId('ff-inbound-create-cargo-places').click();
   await f.page.getByRole('dialog').waitFor();
   assert.match(await f.page.getByRole('dialog').innerText(),/Количество/);
   await capture(f,operation+'-cargo-neighbor');
   await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   await f.page.getByTestId('ff-inbound-box-print-672-box-1').click();
   await f.page.getByTestId('ff-inbound-box-print-dialog-confirm').waitFor();
   await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   await confirm(f); await f.page.getByRole('alert').waitFor();
   assert.equal(f.marks(),0); assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),0);
   const error=await f.page.getByRole('alert').innerText();
   assert.match(error,/WMS672 decode failed at 2/);
   assert.equal(await f.page.getByTestId('ff-inbound-boxes-print-all').isEnabled(),true);
   await capture(f,operation+'-error');
   await f.page.evaluate(()=>{window.__wms672Fault={};});
   await confirm(f); const [job]=await transfer(f);
   const preview=await f.context.newPage(); await preview.setContent(job.html);
   await preview.locator('img').evaluateAll(images=>Promise.all(images.map(i=>i.decode())));
   assert.equal(await preview.locator('.label').count(),3);
   assert.deepEqual(await preview.locator('.label').evaluateAll(rows=>rows.map(r=>r.getAttribute('data-barcode'))),['INB-000000000001','INB-000000000002','INB-000000000003']);
   await preview.screenshot({path:resolve(evidence,operation+'-full-preview.png'),fullPage:true});
   await writeFile(resolve(evidence,operation+'-preview.html'),job.html);
   await writeFile(resolve(evidence,operation+'-placement.json'),JSON.stringify({layout,error,previewLabels:3,neighborDialogs:['cargo','individual box'],externalWrites:f.calls.filter(c=>c.method!=='GET'&&!c.path.endsWith('/mark-label-printed'))},null,2));
   assert.equal(f.calls.filter(c=>c.method!=='GET'&&!c.path.endsWith('/mark-label-printed')).length,0);
  } finally {await f.context.close();}
 });
}

for (const operation of ['inbound','return']) {
 test(`C10 remaining ${operation}: existing WMS659 bulk creation opens quantity dialog without printing`,async()=>{
  const f=await fixture(3,operation);
  try {
   await f.page.getByTestId('ff-inbound-add-to-box').click();
   await f.page.waitForTimeout(500); // only diagnostic UI settling, never approval
   await capture(f,operation+'-659-integration');
   assert.equal(await f.page.evaluate(()=>window.__wms672Transfers.length),0);
   assert.equal(f.calls.filter(c=>c.method!=='GET').length,0,'opening WMS659 creation must not immediately mutate');
   assert.equal(await f.page.getByRole('dialog').count(),1,'existing WMS659 quantity dialog must open');
   assert.match(await f.page.getByRole('dialog').innerText(),/Количество коробов/);
  } finally {await f.context.close();}
 });
}
