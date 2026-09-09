#!/usr/bin/env node
'use strict';
// One owned stage MP document; real responses only. No WMS084/FBS mutations.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const WEB = 'https://web-production-9e7c1.up.railway.app';
const MP = '/operations/marketplace-unload-requests';
const TENANT = '9c31f3f4-ce62-4c1f-891a-295b278f1e69';
const SELLER = '50110328-fa03-4604-b2e4-8ca27fc8bb41';
const WAREHOUSE = '307c0ccd-9a6b-41df-9180-f8ed68022237';
const PRODUCT = '45587c50-451f-4d0a-b233-98c07be4dc9d';
const BARCODE = '2000000000013';
const A = '817b4384-17ba-4872-9a81-d8f62adc3dfe';
const B = '7b100aa1-54c8-4efc-bd61-2bf1e1453374';
const SHA = '50c9c88e0e56097e857fa26e0bda419d69125f9f';
const execute = process.argv[2] === '--execute-red-approved';
assert.equal(process.argv.length, execute ? 3 : 2);
const token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt', 'utf8').trim().replace(/^Bearer\s+/i, '');
const output = path.resolve(__dirname, '../wms058-queued-source-20260909');
const evidence = { label: 'WMS058 queue-source RED', started: new Date().toISOString(), sha: SHA, requests: [], states: {}, cleanup: [] };
let docId, browser, release422;
function save() { fs.mkdirSync(output, { recursive: true }); fs.writeFileSync(path.join(output, 'red.json'), JSON.stringify(evidence, null, 2) + '\n'); }
function allowed(p, m) {
  if (['GET', 'HEAD', 'OPTIONS'].includes(m)) return true;
  return execute && m === 'POST' && (p === MP || (docId && (['lines', 'confirm', 'cancel', 'boxes'].some(s => p === `${MP}/${docId}/${s}`) || p.startsWith(`${MP}/${docId}/boxes/`) && p.endsWith('/scan'))));
}
async function api(p, method = 'GET', body) {
  assert(allowed(p.split('?')[0], method));
  const r = await fetch(`${WEB}/api${p}`, { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(30000) });
  const d = r.status === 204 ? null : await r.json();
  assert(r.ok, `${method} ${p} returned ${r.status}`);
  return d;
}
function physical() {
  const py = `import asyncio,json,os
from sqlalchemy import text
from app.db.session import SessionLocal
async def main():
 async with SessionLocal() as s:
  await s.execute(text('SET TRANSACTION READ ONLY'))
  await s.execute(text("SET LOCAL statement_timeout='8s'"))
  qs={
   'product':"SELECT id,seller_id,sku_code FROM products WHERE tenant_id='${TENANT}' AND id='${PRODUCT}'",
   'balances':"SELECT b.id,b.storage_location_id,b.container_kind,b.container_id,b.quantity,b.quantity_unpacked,b.quantity_packed,l.warehouse_id,w.internal_barcode FROM inventory_balances b JOIN storage_locations l ON l.id=b.storage_location_id LEFT JOIN warehouse_boxes w ON w.id=b.container_id AND w.tenant_id=b.tenant_id WHERE b.tenant_id='${TENANT}' AND b.product_id='${PRODUCT}' ORDER BY b.id",
   'movements':"SELECT id,storage_location_id,container_kind,container_id,quantity_delta,movement_type FROM inventory_movements WHERE tenant_id='${TENANT}' AND product_id='${PRODUCT}' ORDER BY id"
  }
  out={k:[dict(r) for r in (await s.execute(text(q))).mappings()] for k,q in qs.items()}
  out['sha']=os.environ.get('RAILWAY_GIT_COMMIT_SHA')
  print('WMS058='+json.dumps(out,default=str))
asyncio.run(main())`;
  const raw = execFileSync('railway', ['ssh', '--project', 'c28e681d-4535-4c96-ac97-c7b600a7f8e4', '--environment', '58a08b66-1290-45a2-8737-e3d7408389e5', '--service', 'WMS', '--', 'python', '-c', py], { encoding: 'utf8', timeout: 45000, stdio: ['ignore', 'pipe', 'pipe'] });
  const s = JSON.parse(raw.split('\n').find(l => l.startsWith('WMS058=')).slice(7));
  assert.equal(s.sha, SHA); assert.equal(s.product[0].seller_id, SELLER); assert.equal(s.product[0].sku_code, 'EMU-KIZ-OPTIONAL');
  return s;
}
const quantity = (s, id) => s.balances.filter(b => b.container_id === id).reduce((n,b) => n+b.quantity, 0);
const total = s => s.balances.reduce((n,b) => n+b.quantity, 0);
async function state(name) { const s = physical(); evidence.states[name] = { physical: s, detail: await api(`${MP}/${docId}`), options: await api(`${MP}/${docId}/pick-options`) }; save(); return s; }
async function main() {
  const me = await api('/auth/me'); assert.equal(me.tenant_id, TENANT); assert.equal(me.role, 'fulfillment_admin');
  const before = physical(); evidence.states.before_create = { physical: before };
  assert(quantity(before,A)>=2 && quantity(before,B)>=1);
  for (const id of [A,B]) assert(before.balances.filter(b=>b.container_id===id&&b.quantity>0).every(b=>b.warehouse_id===WAREHOUSE));
  if (!execute) { console.log(JSON.stringify({ result:'READ_ONLY_PREFLIGHT_PASS', sourceA:quantity(before,A),sourceB:quantity(before,B),sha:before.sha })); return; }
  try {
    const doc = await api(MP, 'POST', { seller_id: SELLER, warehouse_id: WAREHOUSE, wb_mp_warehouse_id:507 });
    docId=doc.id; evidence.document=doc; save();
    await api(`${MP}/${docId}/lines`, 'POST', { product_id: PRODUCT, quantity:1 });
    await api(`${MP}/${docId}/confirm`, 'POST', { planned_shipment_date:new Date(Date.now()+86400000).toISOString().slice(0,10) });
    const box=await api(`${MP}/${docId}/boxes`, 'POST', { box_preset:'60_40_40' }); evidence.box=box;
    const options=await api(`${MP}/${docId}/pick-options`); const option=options.find(o=>o.product_id===PRODUCT); assert(option);
    const source=(id)=>option.locations.flatMap(l=>l.sources.map(s=>({...s,location:l.storage_location_id}))).find(s=>s.container_path.at(-1)?.id===id);
    const sa=source(A),sb=source(B); assert(sa?.available>=2&&sb?.available>=1); evidence.sourceA=sa;evidence.sourceB=sb;save();
    const codeA=sa.container_path.at(-1).code,codeB=sb.container_path.at(-1).code;assert(codeA&&codeB);
    const scanPath=`${MP}/${docId}/boxes/${box.id}/scan`;
    const {chromium}=require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    await context.addInitScript(({origin,t})=>{if(location.origin===origin)localStorage.setItem('wms_token_ff',t)}, {origin:WEB,t:token});
    let hold=false,heldResolve;const held=new Promise(r=>heldResolve=r);const barrier=new Promise(r=>release422=r);
    await context.route('**/*',async route=>{
      const req=route.request(),u=new URL(req.url());
      if(!['GET','HEAD','OPTIONS'].includes(req.method())&&(u.origin!==WEB||!u.pathname.startsWith('/api/')||!allowed(u.pathname.slice(4),req.method())))return route.abort();
      if(u.origin===WEB&&u.pathname===`/api${scanPath}`&&req.method()==='POST'){
        const body=req.postDataJSON();evidence.requests.push({time:new Date().toISOString(),body});
        if(hold&&body.barcode===BARCODE&&!body.allow_over_plan){
          hold=false;const response=await route.fetch();const raw=await response.body();const parsed=JSON.parse(raw.toString());
          evidence.delayedResponse={status:response.status(),body:parsed};assert.equal(response.status(),422);assert.equal(parsed.detail,'plan_limit_exceeded');
          heldResolve();await barrier;return route.fulfill({response,body:raw});
        }
      }
      return route.continue();
    });
    const page=await context.newPage();await page.goto(`${WEB}/ff/mp-shipments?open_mp=${docId}`);
    await page.getByRole('tab',{name:/^Упаковка/}).click();const fill=page.getByTestId(`ff-mp-box-add-products-${box.id}`);if(!await fill.isVisible())await page.getByText('Короба',{exact:true}).click();await fill.click();
    const input=page.getByTestId('ff-mp-box-add-scan-input');await input.waitFor();
    async function scan(code){const pending=page.waitForResponse(r=>r.url().endsWith(scanPath)&&r.request().method()==='POST');await input.fill(code);await input.press('Enter');const r=await pending;assert.equal(r.status(),200);return r.json();}
    assert.equal((await scan(codeA)).container_id,A);await page.getByTestId('ff-mp-box-add-active-location').filter({hasText:codeA}).waitFor();
    await scan(BARCODE);await page.waitForFunction(pid=>document.querySelector(`[data-testid="ff-mp-box-add-row-${pid}"]`)?.querySelectorAll('td')[4]?.textContent==='1',PRODUCT);
    const baseline=await state('plan_fulfilled');assert.equal(quantity(baseline,A),quantity(before,A)-1);
    hold=true;await input.fill(BARCODE);await input.press('Enter');await Promise.race([held,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Real422 not captured')),15000))]);
    await input.fill(codeB);await input.press('Enter');evidence.queuedBWhileReal422Held=true;
    const bResponse=page.waitForResponse(r=>r.url().endsWith(scanPath)&&r.request().postDataJSON()?.barcode===codeB);
    release422();await page.getByTestId('ff-mp-box-add-over-plan-dialog').waitFor();assert.equal((await bResponse).status(),200);
    await page.getByTestId('ff-mp-box-add-active-location').filter({hasText:codeB}).waitFor();
    await page.screenshot({path:path.join(output,'red-modal-source-b.png'),animations:'disabled'});
    const modal=await state('modal_with_b_selected');assert.deepEqual(modal.balances,baseline.balances);assert.deepEqual(modal.movements,baseline.movements);
    const confirmed=page.waitForResponse(r=>r.url().endsWith(scanPath)&&r.request().postDataJSON()?.allow_over_plan===true);
    await page.getByTestId('ff-mp-box-add-over-plan-confirm').click();assert.equal((await confirmed).status(),200);
    const after=await state('after_confirmation');const last=evidence.requests.at(-1).body;
    assert.equal(last.container_id,B);assert.equal(quantity(after,A),quantity(baseline,A));assert.equal(quantity(after,B),quantity(baseline,B)-1);
    evidence.result='RED_CONFIRMED_WRONG_SOURCE';evidence.wrongSource={expected:A,actual:B,confirmedRequest:last};
    await page.screenshot({path:path.join(output,'red-after-confirmation.png'),animations:'disabled'});save();
    console.log(JSON.stringify({result:evidence.result,document:docId,expected:A,actual:B}));
  }finally{
    if(release422)release422();if(browser)await browser.close();evidence.chromeClosed=true;
    if(docId){await api(`${MP}/${docId}/cancel`,'POST',{});const cancelled=await api(`${MP}/${docId}`);evidence.cleanup.push({id:docId,status:cancelled.status});assert.equal(cancelled.status,'cancelled');evidence.states.after_cancel={physical:physical()};assert.equal(total(evidence.states.after_cancel.physical),total(before));}
    save();
  }
}
main().catch(e=>{evidence.result=evidence.result||'FAILED_OR_INCOMPLETE';evidence.error=e.message.replaceAll(token,'[redacted]');if(execute)save();console.error(evidence.error);process.exitCode=1;});
