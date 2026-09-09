#!/usr/bin/env node
'use strict';

// WMS-084 / WMS-395: a one-off, operator-equivalent Chrome check, not a CI suite.
// Default is read-only. Run the mutation mode ONLY after root confirms the app deployment.
// node docs/reviews/scripts/wms084-stage-browser.cjs
// node docs/reviews/scripts/wms084-stage-browser.cjs --execute-after-deployment-ready=<full SHA>
// No tokens, raw marking values, PDFs, or request headers are written to evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const ORIGIN = 'https://web-production-9e7c1.up.railway.app';
const FIXTURE = Object.freeze({
  tenant: '9c31f3f4-ce62-4c1f-891a-295b278f1e69',
  seller: '50110328-fa03-4604-b2e4-8ca27fc8bb41',
  product: '3d6050c5-0d29-4612-9e30-e90ecbf9408a',
  orders: ['cf303d12-426b-4a38-a59f-ac0c18ccb68b', 'b620419c-79b3-4369-beb0-5fdc21c53ddb'],
  wbOrders: [500033, 500035],
  code: '1be09c79-4fd1-465e-9688-a77183af289f',
  pool: '80a718dd-2487-4951-a1dd-9e13aee562e6',
  name: 'WMS-084 QA 2026-09-09 · 500033 → 500035',
  operationKey: 'wms084-browser-20260909-500033-500035',
});
const arg = process.argv.slice(2).find(v => v.startsWith('--execute-after-deployment-ready='));
const approvedSha = arg?.split('=')[1];
if (arg) assert.match(approvedSha, /^[a-f0-9]{40}$/, 'Full deployment SHA required');
assert.equal(process.argv.slice(2).length, arg ? 1 : 0, 'Unknown argument');
const token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt', 'utf8')
  .trim().replace(/^Bearer\s+/i, '');
const output = path.resolve(__dirname, '../wms084-stage-browser-20260909');
const evidence = { fixture: FIXTURE, approvedSha: approvedSha || null, checks: [], snapshots: {} };

async function api(route, method = 'GET', body) {
  assert(route.startsWith('/'), 'Relative API path required');
  if (!approvedSha) assert.equal(method, 'GET', 'Read-only preparation');
  const response = await fetch(`${ORIGIN}/api${route}`, {
    method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(90000),
  });
  assert(response.ok, `${method} ${route}: HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

// This child only reads scoped SQL. Runtime DB credentials remain inside Railway.
function snapshot() {
  const py = `import asyncio,json,os
from urllib.parse import urlsplit
from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.settings import settings
async def main():
 async with SessionLocal() as s:
  await s.execute(text("SET TRANSACTION READ ONLY"))
  await s.execute(text("SET LOCAL statement_timeout='8s'"))
  q={
   'product': "SELECT id,sku_code,name FROM products WHERE tenant_id='${FIXTURE.tenant}' AND seller_id='${FIXTURE.seller}' AND id='${FIXTURE.product}'",
   'orders': "SELECT o.id,o.wb_order_id,o.product_id,o.seller_id,o.supply_id,o.status,o.pick_status,o.pack_status,o.reserve_status,o.sticker_status,o.sticker_barcode FROM fbs_orders o WHERE o.tenant_id='${FIXTURE.tenant}' AND o.seller_id='${FIXTURE.seller}' AND o.id IN ('${FIXTURE.orders.join("','")}') ORDER BY o.wb_order_id",
   'code': "SELECT id,status,source,pool_id,cis_code,packaging_task_line_id,printed_at,applied_at,introduced_at,(label_artifact_pdf IS NOT NULL) AS has_label_artifact FROM marking_codes WHERE tenant_id='${FIXTURE.tenant}' AND seller_id='${FIXTURE.seller}' AND id='${FIXTURE.code}'",
   'bindings': "SELECT m.id,m.order_id,m.marking_code_id,m.kind,m.source,m.meta_status,m.check_status FROM fbs_order_markings m JOIN fbs_orders o ON o.id=m.order_id WHERE o.tenant_id='${FIXTURE.tenant}' AND o.seller_id='${FIXTURE.seller}' AND (m.order_id IN ('${FIXTURE.orders.join("','")}') OR m.marking_code_id='${FIXTURE.code}') ORDER BY m.id",
   'balances': "SELECT id,storage_location_id,container_kind,container_id,quantity,quantity_unpacked,quantity_packed FROM inventory_balances WHERE tenant_id='${FIXTURE.tenant}' AND product_id='${FIXTURE.product}' ORDER BY id",
   'movements': "SELECT id FROM inventory_movements WHERE tenant_id='${FIXTURE.tenant}' AND product_id='${FIXTURE.product}' ORDER BY id",
   'reservations': "SELECT id,fbs_order_id,quantity FROM fbs_order_reservations WHERE tenant_id='${FIXTURE.tenant}' AND product_id='${FIXTURE.product}' AND fbs_order_id IN (SELECT id FROM fbs_orders WHERE tenant_id='${FIXTURE.tenant}' AND seller_id='${FIXTURE.seller}') ORDER BY id"
  }
  result={k:[dict(r) for r in (await s.execute(text(v))).mappings()] for k,v in q.items()}
  result['provider_host']=urlsplit(settings.wildberries_marketplace_api_base).hostname
  result['runtime_sha']=os.environ.get('RAILWAY_GIT_COMMIT_SHA')
  print('WMS084_JSON='+json.dumps(result,default=str))
asyncio.run(main())`;
  let raw;
  try { raw = execFileSync('railway', ['ssh', '--project', 'c28e681d-4535-4c96-ac97-c7b600a7f8e4',
    '--environment', '58a08b66-1290-45a2-8737-e3d7408389e5', '--service', 'WMS', '--', 'python', '-c', py],
  { encoding: 'utf8', timeout: 45000, maxBuffer: 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch { throw new Error('Scoped read-only Railway snapshot failed; inspect query schema separately'); }
  const line = raw.split('\n').find(v => v.startsWith('WMS084_JSON='));
  assert(line, 'Scoped SQL result missing');
  const state = JSON.parse(line.slice('WMS084_JSON='.length));
  assert.equal(state.provider_host, 'wb-emulator.railway.internal', 'Emulator-only guard');
  if (approvedSha && state.runtime_sha) assert.equal(state.runtime_sha, approvedSha, 'Deployment mismatch');
  return state;
}

function remember(name, state) {
  const safe = structuredClone(state);
  for (const code of safe.code) delete code.cis_code;
  evidence.snapshots[name] = safe;
}
function sameInventory(before, after) {
  for (const key of ['balances', 'movements', 'reservations']) assert.deepEqual(after[key], before[key], `${key} changed during KIZ operation`);
}
async function unavailableForPrint() {
  const rows = await api(`/operations/marking-codes/pools/${FIXTURE.pool}/codes?status=available`);
  assert(!rows.some(row => row.id === FIXTURE.code), 'Detached physical code reentered available print pool');
}
function save() {
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
}

async function main() {
  const me = await api('/auth/me');
  assert.equal(me.tenant_id, FIXTURE.tenant);
  assert.equal(me.role, 'fulfillment_admin');
  const beforeSetup = snapshot();
  assert.equal(beforeSetup.orders.length, 2);
  assert.equal(beforeSetup.code.length, 1);
  assert.equal(beforeSetup.bindings.length, 0, 'Fixture already used; stop, do not reset it');
  for (const order of beforeSetup.orders) {
    assert.equal(order.status, 'new');
    assert.equal(order.supply_id, null);
    assert.equal(order.product_id, FIXTURE.product);
    assert.equal(order.seller_id, FIXTURE.seller);
  }
  assert.equal(beforeSetup.code[0].status, 'available');
  assert.equal(beforeSetup.code[0].pool_id, FIXTURE.pool);
  assert.match(beforeSetup.code[0].cis_code, /^010200000000001521EMU.*STAGE/);
  remember('before_setup', beforeSetup);
  if (!approvedSha) {
    console.log(JSON.stringify({ result: 'READ_ONLY_PREFLIGHT_PASS', fixture: FIXTURE,
      product: beforeSetup.product, provider_host: beforeSetup.provider_host, runtime_sha: beforeSetup.runtime_sha }));
    return;
  }
  const created = await api('/operations/fbs-supplies/from-orders', 'POST', {
    name: FIXTURE.name, order_ids: FIXTURE.orders, planned_delivery_type: 'warehouse_sc',
    idempotency_key: FIXTURE.operationKey,
  });
  const supplyId = created.supply.id;
  evidence.supplyId = supplyId;
  // QR generation only: never issue a marking label or send a job to a printer.
  const stickers = await api(`/operations/fbs-supplies/${supplyId}/print-assets`, 'POST', {
    kind: 'order_sticker', order_ids: FIXTURE.orders,
  });
  const afterSetup = snapshot();
  remember('after_setup', afterSetup);
  save();
  assert(afterSetup.orders.every(order => order.supply_id === supplyId && order.sticker_barcode));
  const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
  let browser;
  try {
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(({ origin, value }) => {
      if (location.origin === origin) localStorage.setItem('wms_token_ff', value);
    }, { origin: ORIGIN, value: token });
    const page = await context.newPage();
    page.on('pageerror', error => evidence.checks.push({ pageerror: error.name }));
    await page.goto(`${ORIGIN}/app/ff/fbs?supply_id=${supplyId}`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('fbs-workspace').waitFor();
    if (!created.supply.packaging_task_id) {
      const started = page.waitForResponse(r => r.url().endsWith(`/${supplyId}/start-work`) && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Начать работу с поставкой', exact: true }).click();
      assert((await started).ok(), 'UI start-work failed');
    }
    await page.getByRole('tab', { name: 'Упаковка и маркировка', exact: true }).click();
    const input = page.getByTestId('fbs-kiz-scan-input').locator('input');
    await input.waitFor({ state: 'visible' });
    for (const order of afterSetup.orders) {
      await page.locator(`[data-order-id="${order.id}"]`).getByTestId('fbs-sticker-code').waitFor();
    }
    // Render the real generated WB sticker images in Chrome; no physical print action.
    assert.equal(stickers.ready, 2, 'Both ordinary order stickers must exist');
    const preview = await context.newPage();
    const images = [];
    for (const asset of stickers.assets) {
      assert.equal(asset.status, 'ready');
      assert.equal(asset.content_type, 'image/png');
      assert(asset.preview_url.startsWith('/operations/'), 'Known sticker API path required');
      const url = new URL(`${ORIGIN}/api${asset.preview_url}`);
      assert.equal(url.origin, ORIGIN, 'Same-origin sticker preview only');
      const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(30000) });
      assert(response.ok(), 'Sticker image unavailable');
      images.push(Buffer.from(await response.arrayBuffer()).toString('base64'));
    }
    await preview.setContent(`<html><body><h1>WMS-084 · WB500033 / WB500035</h1>${images.map(image => `<img style="width:464px;margin:20px" src="data:image/png;base64,${image}">`).join('')}</body></html>`);
    await preview.waitForFunction(() => [...document.images].every(img => img.complete && img.naturalWidth > 0));
    await preview.screenshot({ path: path.join(output, '00-sticker-preview.png') });
    await preview.close();
    remember('after_setup', snapshot());
    const baseline = snapshot();
    remember('before_kiz', baseline);
    const rawCode = baseline.code[0].cis_code;
    async function scan(order) {
      await input.fill(order.sticker_barcode);
      await input.press('Enter');
      await page.getByTestId('fbs-kiz-scan-active').waitFor();
      await input.fill(rawCode);
      const committed = page.waitForResponse(r => r.url().endsWith('/operations/fbs-orders/kiz/commit') && r.request().method() === 'POST');
      await input.press('Enter');
      const response = await committed;
      assert(response.ok(), 'UI KIZ commit failed');
      const rows = await response.json();
      assert(rows.some(row => row.order_id === order.id && row.status === 'ok'), 'UI did not save KIZ');
      await page.locator(`[data-order-id="${order.id}"]`).getByTestId('fbs-kiz-undo-inline').waitFor();
    }
    await scan(baseline.orders[0]);
    const boundA = snapshot();
    remember('bound_a', boundA);
    sameInventory(baseline, boundA);
    assert.equal(boundA.bindings.length, 1);
    assert.equal(boundA.bindings[0].marking_code_id, FIXTURE.code);
    assert.equal(boundA.bindings[0].order_id, FIXTURE.orders[0]);
    await unavailableForPrint();
    await page.screenshot({ path: path.join(output, '01-bound-a.png') });
    await page.locator(`[data-order-id="${FIXTURE.orders[0]}"]`).getByTestId('fbs-kiz-undo-inline').click();
    const dialog = page.getByRole('dialog').filter({ has: page.getByText('Отменить КИЗ?', { exact: true }) });
    const removed = page.waitForResponse(r => r.url().endsWith(`/operations/fbs-orders/${FIXTURE.orders[0]}/kiz`) && r.request().method() === 'DELETE');
    await dialog.getByRole('button', { name: 'Отменить КИЗ', exact: true }).click();
    assert.equal((await removed).status(), 204);
    const detached = snapshot();
    remember('detached', detached);
    sameInventory(baseline, detached);
    assert.equal(detached.bindings.length, 0);
    assert.equal(detached.code[0].id, FIXTURE.code);
    for (const key of ['status', 'source', 'printed_at', 'applied_at', 'introduced_at', 'has_label_artifact']) {
      assert.deepEqual(detached.code[0][key], boundA.code[0][key], `Detach changed ${key}`);
    }
    assert.equal(detached.code[0].packaging_task_line_id, null);
    await unavailableForPrint();
    await page.locator(`[data-order-id="${FIXTURE.orders[0]}"]`).getByTestId('fbs-kiz-undo-inline').waitFor({ state: 'hidden' });
    await page.screenshot({ path: path.join(output, '02-detached.png') });
    await scan(baseline.orders[1]);
    const boundB = snapshot();
    remember('bound_b', boundB);
    sameInventory(baseline, boundB);
    assert.equal(boundB.bindings.length, 1);
    assert.equal(boundB.bindings[0].marking_code_id, FIXTURE.code);
    assert.equal(boundB.bindings[0].order_id, FIXTURE.orders[1]);
    assert.notEqual(boundB.bindings[0].id, boundA.bindings[0].id);
    await unavailableForPrint();
    await page.screenshot({ path: path.join(output, '03-bound-b.png') });
    assert(!evidence.checks.some(check => check.pageerror), 'Browser page error recorded');
    evidence.result = 'PASS';
    evidence.finalState = 'One binding on WB500035; named QA supply retained; no state reset or shipment.';
  } finally {
    if (browser) await browser.close();
    save();
  }
  console.log(JSON.stringify({ result: evidence.result, supplyId, evidence: output }));
}
main().catch(error => {
  // Never dump HTTP bodies, SSH output, token, or scanner input on failure.
  evidence.result = 'FAIL_OR_INCOMPLETE';
  evidence.error = error.message.replaceAll(token, '[redacted]');
  if (approvedSha) save();
  console.error(evidence.error);
  process.exitCode = 1;
});
