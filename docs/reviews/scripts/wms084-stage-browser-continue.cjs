#!/usr/bin/env node
'use strict';
// Existing objects only. Default read-only; execution waits for root's verified deployment SHA.
// node docs/reviews/scripts/wms084-stage-browser-continue.cjs
// node docs/reviews/scripts/wms084-stage-browser-continue.cjs --execute-after-deployment-ready=<new full SHA>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { snapshot, FIXTURE } = require('./wms084-stage-browser.cjs');
const origin = 'https://web-production-9e7c1.up.railway.app';
const supplyId = 'aa3e89c6-68b9-4fd0-a849-2f8fdec0a988';
const previousBinding = 'b0335179-a151-4420-b938-f7a0c4317d1f';
const approvedSha = process.argv[2]?.split('=')[1];
const token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt', 'utf8').trim().replace(/^Bearer\s+/i, '');
const output = path.resolve(__dirname, '../wms084-stage-browser-20260909');
const initial = JSON.parse(fs.readFileSync(path.join(output, 'evidence.json'), 'utf8'));
const baseline = initial.snapshots.before_kiz;
const evidence = { supplyId, fixture: FIXTURE, approvedSha: approvedSha || null, checks: [], snapshots: {} };
function remember(name, state) {
  const safe = structuredClone(state);
  for (const code of safe.code) delete code.cis_code;
  evidence.snapshots[name] = safe;
}
function sameInventory(state) {
  for (const key of ['balances', 'movements', 'reservations']) assert.deepEqual(state[key], baseline[key], `${key} differ from original pre-KIZ baseline`);
}
async function readApi(route) {
  const response = await fetch(`${origin}/api${route}`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(30000) });
  assert(response.ok, `Read-only GET returned ${response.status}`);
  return response.json();
}
async function unavailable() {
  const rows = await readApi(`/operations/marking-codes/pools/${FIXTURE.pool}/codes?status=available`);
  assert(!rows.some(row => row.id === FIXTURE.code), 'Physical code returned to available label pool');
}
function save() {
  fs.writeFileSync(path.join(output, 'continuation.json'), JSON.stringify(evidence, null, 2) + '\n');
}
async function main() {
  const me = await readApi('/auth/me');
  assert.equal(me.tenant_id, FIXTURE.tenant);
  assert.equal(me.role, 'fulfillment_admin');
  const before = snapshot();
  sameInventory(before);
  assert.equal(before.bindings.length, 1);
  assert.equal(before.bindings[0].id, previousBinding);
  assert.equal(before.bindings[0].order_id, FIXTURE.orders[0]);
  assert.equal(before.bindings[0].marking_code_id, FIXTURE.code);
  assert.equal(before.code[0].status, 'applied');
  assert(before.orders.every(order => order.supply_id === supplyId));
  await unavailable();
  remember('before_cancel', before);
  if (!approvedSha) {
    console.log(JSON.stringify({ result: 'READ_ONLY_CONTINUATION_PREFLIGHT_PASS', supplyId, currentBinding: previousBinding, runtimeSha: before.runtime_sha }));
    return;
  }
  assert.notEqual(approvedSha, '27400e5ff45d4e93eb6afc174f60710f3930abb4', 'Old deployment has no pool-code inline cancellation');
  const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
  let browser;
  try {
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(({ origin, token }) => {
      if (location.origin === origin) localStorage.setItem('wms_token_ff', token);
    }, { origin, token });
    const page = await context.newPage();
    page.on('pageerror', error => evidence.checks.push({ pageerror: error.name }));
    await page.goto(`${origin}/app/ff/fbs?supply_id=${supplyId}`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('tab', { name: 'Упаковка и маркировка', exact: true }).click();
    const rowA = page.locator(`[data-order-id="${FIXTURE.orders[0]}"]`);
    await rowA.getByTestId('fbs-kiz-undo-inline').waitFor();
    await page.screenshot({ path: path.join(output, '02-inline-a-after-fix.png') });
    await rowA.getByTestId('fbs-kiz-undo-inline').click();
    const dialog = page.getByRole('dialog').filter({ has: page.getByText('Отменить КИЗ?', { exact: true }) });
    await dialog.waitFor();
    await page.screenshot({ path: path.join(output, '03-inline-confirmation.png') });
    const removed = page.waitForResponse(r => r.url().endsWith(`/operations/fbs-orders/${FIXTURE.orders[0]}/kiz`) && r.request().method() === 'DELETE');
    await dialog.getByRole('button', { name: 'Отменить КИЗ', exact: true }).click();
    assert.equal((await removed).status(), 204, 'Actual UI cancellation failed');
    const detached = snapshot();
    remember('detached', detached);
    save();
    sameInventory(detached);
    assert.equal(detached.bindings.length, 0);
    assert.equal(detached.code[0].id, FIXTURE.code);
    assert.equal(detached.code[0].packaging_task_line_id, null);
    for (const key of ['status', 'source', 'printed_at', 'applied_at', 'introduced_at', 'has_label_artifact']) assert.deepEqual(detached.code[0][key], before.code[0][key], `Cancel changed physical code ${key}`);
    await unavailable();
    await rowA.getByTestId('fbs-kiz-undo-inline').waitFor({ state: 'hidden' });
    await page.screenshot({ path: path.join(output, '04-detached-a.png') });
    const input = page.getByTestId('fbs-kiz-scan-input').locator('input');
    const orderB = before.orders.find(order => order.id === FIXTURE.orders[1]);
    assert(orderB.sticker_barcode, 'Existing B sticker must be available');
    await input.fill(orderB.sticker_barcode);
    await input.press('Enter');
    await page.getByTestId('fbs-kiz-scan-active').waitFor();
    await input.fill(before.code[0].cis_code);
    const committed = page.waitForResponse(r => r.url().endsWith('/operations/fbs-orders/kiz/commit') && r.request().method() === 'POST');
    await input.press('Enter');
    const response = await committed;
    assert(response.ok(), 'Actual B scan commit failed');
    const rows = await response.json();
    assert(rows.some(row => row.order_id === FIXTURE.orders[1] && row.status === 'ok'));
    const boundB = snapshot();
    remember('bound_b', boundB);
    save();
    sameInventory(boundB);
    assert.equal(boundB.bindings.length, 1);
    assert.equal(boundB.bindings[0].order_id, FIXTURE.orders[1]);
    assert.equal(boundB.bindings[0].marking_code_id, FIXTURE.code);
    assert.notEqual(boundB.bindings[0].id, previousBinding);
    assert.equal(boundB.code[0].id, FIXTURE.code);
    assert.equal(boundB.code[0].status, 'applied');
    await unavailable();
    await page.locator(`[data-order-id="${FIXTURE.orders[1]}"]`).getByTestId('fbs-kiz-undo-inline').waitFor();
    await page.screenshot({ path: path.join(output, '05-bound-b.png') });
    assert(!evidence.checks.some(check => check.pageerror));
    evidence.result = 'PASS';
    evidence.finalState = 'Same physical code applied, one new binding on WB500044; no reset, setup, picking or shipment.';
  } finally {
    if (browser) await browser.close();
    evidence.chromeClosed = true;
    save();
  }
  console.log(JSON.stringify({ result: evidence.result, supplyId, evidence: path.join(output, 'continuation.json') }));
}
main().catch(error => {
  evidence.result = 'FAIL_OR_INCOMPLETE';
  evidence.error = error.message.replaceAll(token, '[redacted]');
  if (approvedSha) save();
  console.error(evidence.error);
  process.exitCode = 1;
});
