'use strict';

// SC17 test-first contract. Synthetic API and DOM boundary; no real browser,
// production data, certificate, signature, operation or network is used.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const directory = process.env.WMS517_MAC_SOURCE_DIR ?? path.join(__dirname, '..');
const { createHelper } = require(path.join(directory, 'avpack-sold-kiz-filter.js'));
const historicalIds = require('./fixtures/wms517-historical80-row-ids.json');
const TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
const SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
const TOKEN = 'synthetic-session-do-not-return';
const ORIGIN = 'https://wms.sellerfocus.pro';
const REGISTRY = '/api/operations/marking-codes/self/withdrawals';
const row = (id) => ({ row_id: id, status: 'not_withdrawn', operation_id: null,
  error: null, resume_required: false, cis: `synthetic-cis-${id}`, wb_order_id: `order-${id}` });
const rowsFor = (n) => Array.from({ length: n }, (_, i) => row(historicalIds[i] ?? `new-sale-${i}`));
const usable = (r) => r.status === 'not_withdrawn' && r.operation_id === null && !r.error;
function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function harness(options = {}) {
  const calls = [], events = [], selectedIds = [];
  let token = options.token === undefined ? TOKEN : options.token, authCalls = 0;
  let rows = options.rows ?? rowsFor(84);
  let filters = { date_from: '2026-09-18', date_to: '2026-09-25', product_id: 'old-product', search: 'old-search' };
  const identity = { tenant_id: TENANT, seller_id: SELLER, active_seller_id: SELLER,
    role: 'fulfillment_seller', withdrawal_enabled: true, ...options.identity };
  const root = { location: { origin: ORIGIN, pathname: '/seller/honest-sign/withdrawals', ...options.location },
    localStorage: { getItem: () => token }, Response,
    cadesplugin: { sign() { throw new Error('helper must never sign'); } } };
  const originalFetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, ORIGIN);
    const method = String(init.method ?? input?.method ?? 'GET').toUpperCase();
    calls.push({ url, method });
    if (url.pathname === '/api/auth/me') {
      authCalls += 1;
      return response(authCalls > 1 && options.switchIdentity ? { ...identity, seller_id: 'foreign' } : identity,
        options.authStatus ?? 200);
    }
    if (url.pathname !== REGISTRY || method !== 'GET') {
      throw new Error('No create/auth-signature/document-signature/submit request is permitted in preparation');
    }
    const offset = Number(url.searchParams.get('offset') ?? 0);
    const limit = Number(url.searchParams.get('limit') ?? 50);
    if (options.switchTokenAtOffset === offset) token = 'other-session';
    if (options.httpAtOffset === offset) return response({ detail: TOKEN }, options.httpStatus ?? 503);
    if (options.invalidJsonAtOffset === offset) return new Response('{broken');
    let page = { rows: rows.slice(offset, offset + limit), total: rows.length };
    if (options.page) page = options.page(page, offset);
    return response(page);
  };
  root.fetch = originalFetch;
  const ui = {
    async inspectSelection() { events.push('inspect'); return { selectedCount: options.selectedCount ?? 0 }; },
    async clearFilters() { events.push('clear-filters'); filters = {}; },
    async refreshSelectAllAndOpen(n, assertCurrentSession) {
      events.push('open');
      assert.deepEqual(filters, {}, 'all must clear both handover dates, product and search before UI refresh');
      if (options.changeRowsInUi) rows = options.changeRowsInUi(rows);
      if (options.changeTokenInUi) token = 'other-session';
      assertCurrentSession();
      const observed = [];
      let total;
      for (let offset = 0; total === undefined || offset < total; offset += 250) {
        const result = await root.fetch(`${ORIGIN}${REGISTRY}?only_not_withdrawn=true&limit=250&offset=${offset}`);
        const page = await result.json(); total = page.total; observed.push(...page.rows);
      }
      const expected = rows.filter(usable).map(r => r.row_id);
      const actual = observed.filter(usable).map(r => r.row_id);
      assert.deepEqual(actual, expected, 'DOM must see the exact fresh server set, never a stale local snapshot');
      assert.equal(n, expected.length, 'dynamic count must cover every eligible page');
      selectedIds.push(...actual);
      return { selectedCount: options.openedCount ?? n, dialogOpen: options.dialogOpen ?? true };
    },
    async rollbackPreparation() { events.push('rollback'); selectedIds.length = 0; },
  };
  const helper = createHelper({ root, ui });
  return { helper, root, calls, events, selectedIds, originalFetch,
    setToken(value) { token = value; }, get rows() { return rows; } };
}
function safeResult(result, h) {
  assert.equal(result.noSend, true); assert.equal(result.signed, false); assert.equal(result.sent, false);
  const rendered = JSON.stringify(result);
  for (const secret of [TOKEN, ...h.rows.map(r => r.cis)]) assert.ok(!rendered.includes(secret));
  assert.ok(h.calls.every(c => c.method === 'GET'));
  assert.ok(h.calls.every(c => c.url.origin === ORIGIN && ['/api/auth/me', REGISTRY].includes(c.url.pathname)));
}
async function safelyRejects(h, mode = 'execute') {
  await assert.rejects(() => h.helper.run({ mode }), error => {
    assert.ok(error instanceof Error && error.message.length > 0);
    assert.ok(!`${error.message} ${error.stack}`.includes(TOKEN)); return true;
  });
  assert.ok(h.calls.every(c => c.method === 'GET'));
  assert.equal(h.root.fetch, h.originalFetch, 'failed preparation restores original transport');
  assert.deepEqual(h.selectedIds, []);
}

for (const count of [1, 80, 81, 84, 305, 501]) {
  for (const mode of ['dry-run', 'execute']) {
    test(`SC17 ${mode} uses all ${count} fresh eligible sales-backed rows without fixed80`, async () => {
      const h = harness({ rows: rowsFor(count) });
      const result = await h.helper.run({ mode });
      assert.equal(result.targetCount, count);
      assert.equal(result.status, mode === 'execute' ? 'certificate_dialog_open' : 'ready');
      safeResult(result, h);
      const registry = h.calls.filter(c => c.url.pathname === REGISTRY);
      for (const offset of Array.from({ length: Math.ceil(count / 250) }, (_, i) => String(i * 250))) {
        assert.ok(registry.some(c => c.url.searchParams.get('offset') === offset), `missing page ${offset}`);
      }
      for (const call of registry) for (const key of ['date_from', 'date_to', 'product_id', 'search']) {
        assert.ok(!call.url.searchParams.get(key), `${key} must not narrow the complete preparation`);
      }
      if (mode === 'execute') assert.deepEqual(h.selectedIds, h.rows.map(r => r.row_id));
      else { assert.deepEqual(h.events, ['inspect']); assert.equal(h.root.fetch, h.originalFetch); }
    });
  }
}
for (const mode of ['dry-run', 'execute']) {
  test(`SC17 zero rows never claims readiness or opens certificate dialog (${mode})`, async () => {
    const h = harness({ rows: [] });
    const result = await h.helper.run({ mode }).catch(error => error);
    if (!(result instanceof Error)) {
      assert.equal(result.status, 'empty'); assert.equal(result.targetCount, 0); safeResult(result, h);
    }
    assert.ok(!h.events.includes('open')); assert.deepEqual(h.selectedIds, []);
  });
}
for (const [name, mutate] of [
  ['former ID disappeared from sales-backed registry', rows => rows.slice(1)],
  ['return removes former ID and adds a new sold row', rows => [...rows.slice(1), row('sale-after-return')]],
  ['active claim on former ID is excluded', rows => rows.map((r, i) => i ? r : { ...r, operation_id: 'active-op', status: 'awaiting_crpt' })],
  ['already withdrawn former ID is excluded', rows => rows.map((r, i) => i ? r : { ...r, status: 'withdrawn' })],
  ['invalid sale price stays visible but is not selected', rows => rows.map((r, i) => i ? r : { ...r, status: 'error', error: { code: 'wb_price_missing' } })],
]) {
  test(`SC17 ${name}: selects only current eligible IDs`, async () => {
    const h = harness({ rows: mutate(rowsFor(84)) });
    const result = await h.helper.run({ mode: 'execute' });
    assert.equal(result.targetCount, h.rows.filter(usable).length);
    assert.deepEqual(h.selectedIds, h.rows.filter(usable).map(r => r.row_id)); safeResult(result, h);
  });
}
test('SC17 newly returned/claimed ID between read and selection cannot survive as stale snapshot', async () => {
  const h = harness({ changeRowsInUi: rows => rows.slice(1) });
  await safelyRejects(h);
});
test('SC17 same count but replacement ID between read and selection cannot be stale success', async () => {
  const h = harness({ changeRowsInUi: rows => [...rows.slice(1), row('replacement-new-sale')] });
  const outcome = await h.helper.run({ mode: 'execute' }).catch(e => e);
  if (!(outcome instanceof Error)) {
    assert.deepEqual(h.selectedIds, h.rows.map(r => r.row_id)); safeResult(outcome, h);
  } else assert.deepEqual(h.selectedIds, []);
});
for (const [name, options] of [
  ['duplicate across pages', { rows: [...rowsFor(305), row(historicalIds[0])] }],
  ['empty nonterminal page', { page: (p, o) => o === 250 ? { ...p, rows: [] } : p }],
  ['short nonterminal first page', { page: (p, o) => o === 0 ? { ...p, rows: p.rows.slice(0, 20) } : p }],
  ['short terminal page', { page: (p, o) => o === 250 ? { ...p, rows: p.rows.slice(0, 10) } : p }],
  ['changed total on second page', { page: (p, o) => o === 250 ? { ...p, total: p.total + 1 } : p }],
  ['invalid total', { page: p => ({ ...p, total: '305' }) }],
  ['oversized page', { page: p => ({ ...p, rows: rowsFor(251) }) }],
  ['second-page invalid JSON', { invalidJsonAtOffset: 250 }],
  ...[401, 403, 429, 503].map(httpStatus => [`second-page HTTP ${httpStatus}`, { httpAtOffset: 250, httpStatus }]),
]) {
  test(`SC17 ${name} refuses partial or ambiguous preparation before dialog`, async () => {
    const h = harness({ rows: rowsFor(305), ...options }); await safelyRejects(h);
    assert.ok(!h.events.includes('open'));
  });
}
for (const [field, value] of [['tenant_id','wrong'], ['seller_id','wrong'], ['active_seller_id','wrong'],
  ['role','fulfillment_admin'], ['withdrawal_enabled',false]]) {
  test(`SC17 wrong ${field} rejects before registry or UI`, async () => {
    const h = harness({ identity: { [field]: value } }); await safelyRejects(h);
    assert.deepEqual(h.calls.map(c => c.url.pathname), ['/api/auth/me']); assert.deepEqual(h.events, []);
  });
}
for (const location of [{ origin:'https://sellerfocus.pro' }, { origin:'https://foreign.example' },
  { origin:'https://wms.sellerfocus.pro.evil.test' }, { origin:'http://wms.sellerfocus.pro' }, { pathname:'/seller/orders' }]) {
  test(`SC17 exact production origin and route required ${JSON.stringify(location)}`, async () => {
    const h = harness({ location }); await safelyRejects(h); assert.equal(h.calls.length, 0); assert.deepEqual(h.events, []);
  });
}
for (const options of [{ switchTokenAtOffset:250 }, { changeTokenInUi:true }, { switchIdentity:true }]) {
  test(`SC17 seller session switch refuses preparation ${JSON.stringify(options)}`, async () => {
    const h = harness({ rows: rowsFor(305), ...options }); await safelyRejects(h);
  });
}
test('SC17 preexisting selection is not silently extended', async () => {
  const h = harness({ selectedCount:1 }); await safelyRejects(h); assert.ok(!h.events.includes('open'));
});
for (const options of [{ openedCount:83 }, { dialogOpen:false }]) {
  test(`SC17 incomplete DOM confirmation is never success ${JSON.stringify(options)}`, async () => {
    const h = harness(options); await safelyRejects(h); assert.ok(h.events.includes('rollback'));
  });
}

for (const token of [null, '']) {
  test(`SC17 missing seller token ${JSON.stringify(token)} rejects before any GET or UI`, async () => {
    const h = harness({ token }); await safelyRejects(h);
    assert.equal(h.calls.length, 0); assert.deepEqual(h.events, []);
  });
}
for (const authStatus of [401, 403]) {
  test(`SC17 identity GET HTTP ${authStatus} refuses preparation`, async () => {
    const h = harness({authStatus}); await safelyRejects(h);
    assert.deepEqual(h.calls.map(c=>c.url.pathname), ['/api/auth/me']); assert.deepEqual(h.events, []);
  });
}
