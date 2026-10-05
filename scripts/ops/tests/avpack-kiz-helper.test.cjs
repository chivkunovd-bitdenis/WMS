'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { createHelper, TARGETS } = require('../avpack-kiz-helper.js');

// Contract fixtures are independent of the implementation's allowlist.
const TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
const SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
const TOKEN = 'synthetic-test-token-do-not-return';
const ORIGIN = 'https://sellerfocus.pro';
const REGISTRY = '/api/operations/marking-codes/self/withdrawals';
const BILLING_BLOCKER = 'seller_billing_inn_missing_or_invalid';
const EXPECTED = [
  { row_id: 'c9391ebe-21f5-4b1a-89c4-1607563e341a', wb_order_id: '5803306927', cis: '0104630726321651215a0cGXmjtLjxb\u001d91EE12\u001d92lFBvJUaWv6uayEvcOEBE6q/Rlg8WDCxojleoRlHA+uE=' },
  { row_id: 'd79b900c-7bdb-4cbf-840c-3abe6efb9299', wb_order_id: '5800165076', cis: '0104630726321637215G0(VhN1qGejx\u001d91EE12\u001d92zWp5IYlZWPYukhvkOJoKjtO1gO9qgBvrdHWJOoy6oF4=' },
  { row_id: '9cfeb72a-197c-41cf-9402-89792a729d8e', wb_order_id: '5807803330', cis: '0104630726321620215XPXiykjErJGW\u001d91EE12\u001d92AFbVYzMNOCgHlYOPDbHU2znQYBQsUWJuQVNo4UwnyBE=' },
  { row_id: 'c5219133-721a-41b3-b6a4-093c575daeeb', wb_order_id: '5809136493', cis: '0104630726321637215gtDu&gVcNBGs\u001d91EE12\u001d924lJI5/yBasFN8IZWHr6IlQomd/SogonGm8RUx1ydqO4=' },
];

function row(target, overrides = {}) {
  return { ...target, status: 'not_withdrawn', operation_id: null, ...overrides };
}

function harness(options = {}) {
  const calls = [];
  const inspections = [];
  const mutations = [];
  const events = [];
  const identity = {
    tenant_id: TENANT, seller_id: SELLER, active_seller_id: SELLER,
    role: 'fulfillment_seller', withdrawal_enabled: true,
    ...options.identity,
  };
  const rows = options.rows ?? EXPECTED.map(target => row(target));
  const deps = {
    location: { origin: ORIGIN, pathname: '/seller/honest-sign/withdrawals', ...options.location },
    storage: { getItem(key) { assert.equal(key, 'wms_token_seller'); return TOKEN; } },
    fetch: async (input, init = {}) => {
      const url = new URL(String(input), ORIGIN);
      const method = (init.method ?? 'GET').toUpperCase();
      calls.push({ url, init, method });
      events.push(url.pathname);
      assert.equal(url.origin, ORIGIN);
      assert.equal(method, 'GET', 'helper must never mutate through the network');
      assert.equal(init.body, undefined, 'read requests have no payload');
      const headers = new Headers(init.headers);
      assert.equal(headers.get('authorization'), `Bearer ${TOKEN}`);
      if (options.httpFailure === url.pathname) {
        return { ok: false, status: 503, json: async () => ({ detail: TOKEN }), text: async () => TOKEN };
      }
      if (url.pathname === '/api/auth/me') return { ok: true, status: 200, json: async () => identity };
      assert.equal(url.pathname, REGISTRY, 'no other API endpoint is permitted');
      assert.equal(url.searchParams.get('date_from'), '2026-09-18');
      assert.equal(url.searchParams.get('date_to'), '2026-09-19');
      assert.equal(url.searchParams.get('only_not_withdrawn'), 'true');
      assert.equal(url.searchParams.get('limit'), '250');
      const offset = Number(url.searchParams.get('offset'));
      assert.ok(url.searchParams.has('offset'));
      assert.ok(Number.isInteger(offset) && offset >= 0);
      return { ok: true, status: 200, json: async () => ({ rows: rows.slice(offset, offset + 250), total: rows.length }) };
    },
    ui: {
      async inspectSelection(targets) {
        events.push('inspect');
        inspections.push(structuredClone(targets));
        return { selectedCount: 0, targetsReady: true, ...options.selection };
      },
      async selectAndOpen(targets) {
        events.push('selectAndOpen');
        mutations.push(structuredClone(targets));
      },
    },
    ...options.extraDeps,
  };
  return { helper: createHelper(deps), calls, inspections, mutations, events };
}

function targetIdentity(targets) {
  return targets.map(({ row_id, wb_order_id, cis }) => ({ row_id, wb_order_id: String(wb_order_id), cis }));
}

function assertBlockedDryRun(result, verifiedTargets) {
  assert.equal(result.blocker.code, BILLING_BLOCKER);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes(TOKEN));
  // The result must report verified identities without prescribing its layout.
  for (const target of verifiedTargets) {
    for (const value of Object.values(target)) {
      assert.ok(serialized.includes(JSON.stringify(value)), `missing verified value for ${target.wb_order_id}`);
    }
  }
}

async function assertBillingBlocked(h, input) {
  await assert.rejects(() => h.helper.run(input), error => {
    assert.ok(error.code === BILLING_BLOCKER || error.message.includes(BILLING_BLOCKER));
    assert.ok(!String(error.stack).includes(TOKEN));
    return true;
  });
  assert.deepEqual(h.events, ['/api/auth/me', REGISTRY]);
  assert.equal(h.inspections.length, 0, 'known blocker stops before any UI access');
  assert.equal(h.mutations.length, 0);
}

async function failsSafely(h, input) {
  await assert.rejects(async () => h.helper.run(input), error => {
    assert.ok(error instanceof Error);
    assert.ok(!String(error.stack).includes(TOKEN), 'errors must not reveal the token');
    return true;
  });
  assert.equal(h.mutations.length, 0, 'failed checks must not touch selection or certificate dialog');
  for (const call of h.calls) {
    assert.equal(call.method, 'GET');
    assert.equal(call.init.body, undefined);
    assert.equal(call.url.origin, ORIGIN);
    assert.ok(['/api/auth/me', REGISTRY].includes(call.url.pathname));
  }
}

test('the exported allowlist contains exactly the four verified full CIS values', () => {
  assert.deepEqual(targetIdentity(TARGETS), EXPECTED);
});

test('the standalone script exposes the browser global without making requests on load', () => {
  const context = vm.createContext({});
  vm.runInContext(readFileSync(require.resolve('../avpack-kiz-helper.js'), 'utf8'), context);
  assert.equal(typeof context.AvpackKizHelper.createHelper, 'function');
  assert.equal(context.AvpackKizHelper.TARGETS.length, 4);
});

test('default run is read-only and inspects only the first target, never all four', async () => {
  const h = harness();
  const result = await h.helper.run();
  assert.equal(h.mutations.length, 0);
  assert.deepEqual(h.calls.map(call => call.url.pathname), ['/api/auth/me', REGISTRY]);
  assert.equal(h.inspections.length, 1);
  assert.deepEqual(targetIdentity(h.inspections[0]), [EXPECTED[0]]);
  assertBlockedDryRun(result, [EXPECTED[0]]);
});

test('explicit dry-run for multiple allowed orders never selects or opens anything', async () => {
  const h = harness();
  const result = await h.helper.run({ mode: 'dry-run', orderIds: EXPECTED.map(target => target.wb_order_id) });
  assert.equal(h.mutations.length, 0);
  assert.deepEqual(targetIdentity(h.inspections[0]), EXPECTED);
  assertBlockedDryRun(result, EXPECTED);
});

for (const [field, value] of Object.entries({
  tenant_id: 'wrong-tenant', seller_id: 'wrong-seller', active_seller_id: 'wrong-active-seller',
  role: 'admin', withdrawal_enabled: false,
})) {
  test(`identity mismatch in ${field} fails before reading the registry`, async () => {
    const h = harness({ identity: { [field]: value } });
    await failsSafely(h, { mode: 'dry-run' });
    assert.deepEqual(h.calls.map(call => call.url.pathname), ['/api/auth/me']);
  });
}

for (const [name, overrides] of [
  ['changed cryptographic suffix', { cis: EXPECTED[0].cis.slice(0, -1) + 'X' }],
  ['removed group separator', { cis: EXPECTED[0].cis.replaceAll('\u001d', '') }],
  ['different row id', { row_id: 'unverified-row' }],
  ['different WB order', { wb_order_id: '9999999999' }],
  ['in-flight status', { status: 'transferring' }],
  ['already withdrawn', { status: 'withdrawn' }],
  ['linked operation even with not_withdrawn status', { operation_id: 'existing-operation' }],
]) {
  test(`${name} prevents UI mutation`, async () => {
    const h = harness({ rows: [row(EXPECTED[0], overrides)] });
    await failsSafely(h, { mode: 'dry-run' });
  });
}

test('a missing target fails', async () => {
  const h = harness({ rows: EXPECTED.slice(1).map(target => row(target)) });
  await failsSafely(h, { mode: 'dry-run' });
});

test('duplicate matching registry rows fail', async () => {
  const h = harness({ rows: [row(EXPECTED[0]), row(EXPECTED[0])] });
  await failsSafely(h, { mode: 'dry-run' });
});

test('an unapproved order fails before any network request', async () => {
  const h = harness();
  await failsSafely(h, { mode: 'execute', orderIds: ['9999999999'] });
  assert.equal(h.calls.length, 0);
});

test('a preexisting selection is never silently cleared or extended', async () => {
  const h = harness({ selection: { selectedCount: 1 } });
  await failsSafely(h, { mode: 'dry-run' });
});

test('a target absent from the visible selectable UI fails dry-run verification', async () => {
  const h = harness({ selection: { targetsReady: false } });
  await failsSafely(h, { mode: 'dry-run' });
});

test('execute reports the confirmed missing-INN blocker after verification and before any UI', async () => {
  const h = harness();
  await assertBillingBlocked(h, { mode: 'execute', orderIds: [EXPECTED[2].wb_order_id] });
});

test('a run input cannot bypass the confirmed blocker', async () => {
  const h = harness();
  await assertBillingBlocked(h, { mode: 'execute', ignoreBlocker: true });
});

test('a dependency flag cannot bypass the confirmed blocker', async () => {
  const h = harness({ extraDeps: { ignoreBlocker: true } });
  await assertBillingBlocked(h, { mode: 'execute' });
});

for (const path of ['/api/auth/me', REGISTRY]) {
  test(`HTTP failure on ${path} reports status without raw response content`, async () => {
    const h = harness({ httpFailure: path });
    await assert.rejects(() => h.helper.run({ mode: 'execute' }), error => {
      assert.match(error.message, /503/);
      assert.ok(!String(error.stack).includes(TOKEN));
      return true;
    });
    assert.equal(h.mutations.length, 0);
  });
}

for (const location of [
  { origin: 'https://wrong.example' },
  { origin: 'http://sellerfocus.pro' },
  { pathname: '/seller/orders' },
]) {
  test(`wrong host or route fails before network: ${JSON.stringify(location)}`, async () => {
    const h = harness({ location });
    await failsSafely(h, { mode: 'execute' });
    assert.equal(h.calls.length, 0);
  });
}

test('pagination finds an allowed target beyond the first 250 rows', async () => {
  const filler = Array.from({ length: 250 }, (_, index) => row({
    row_id: `unrelated-${index}`, wb_order_id: `unrelated-${index}`, cis: `unrelated-${index}`,
  }));
  const h = harness({ rows: [...filler, row(EXPECTED[0])] });
  const result = await h.helper.run({ mode: 'dry-run' });
  assert.deepEqual(h.calls.filter(call => call.url.pathname === REGISTRY).map(call => call.url.searchParams.get('offset')), ['0', '250']);
  assert.equal(h.mutations.length, 0);
  assert.deepEqual(targetIdentity(h.inspections[0]), [EXPECTED[0]]);
  assertBlockedDryRun(result, [EXPECTED[0]]);
});

test('a duplicate on the second page is detected before opening the dialog', async () => {
  const filler = Array.from({ length: 249 }, (_, index) => row({
    row_id: `unrelated-${index}`, wb_order_id: `unrelated-${index}`, cis: `unrelated-${index}`,
  }));
  const h = harness({ rows: [row(EXPECTED[0]), ...filler, row(EXPECTED[0])] });
  await failsSafely(h, { mode: 'dry-run' });
});

for (const mode of ['sign', 'EXECUTE', '', null]) {
  test(`invalid mode ${JSON.stringify(mode)} fails before network`, async () => {
    const h = harness();
    await failsSafely(h, { mode });
    assert.equal(h.calls.length, 0);
  });
}
