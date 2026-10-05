'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { createHelper, TARGETS } = require('../avpack-kiz-helper.js');

// Contract fixtures are independent of the implementation's allowlist.
const TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
const SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
const TOKEN = 'synthetic-test-token-do-not-return';
const ORIGIN = 'https://sellerfocus.pro';
const REGISTRY = '/api/operations/marking-codes/self/withdrawals';
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
      async selectAndOpen(targets, assertCurrentSession) {
        events.push('selectAndOpen');
        mutations.push(structuredClone(targets));
        assertCurrentSession();
      },
    },
    ...options.extraDeps,
  };
  return { helper: createHelper(deps), calls, inspections, mutations, events };
}

function targetIdentity(targets) {
  return targets.map(({ row_id, wb_order_id, cis }) => ({ row_id, wb_order_id: String(wb_order_id), cis }));
}

function createFakeDom(targets, options = {}) {
  let dialogOpen = false;
  let rows = [];

  const makeCheckbox = (onClick) => ({
    checked: false,
    disabled: false,
    click() {
      this.checked = !this.checked;
      onClick?.(this);
    },
  });
  const makeRow = (target, checkbox) => ({
    querySelectorAll(selector) {
      if (selector === 'a, button') return [{ textContent: target.wb_order_id }];
      if (selector === 'code') {
        const compact = `${target.cis.slice(0, 18)}…${target.cis.slice(-4)}`;
        return [{ textContent: compact }];
      }
      if (selector === 'input[type="checkbox"]') return [checkbox];
      if (selector === '*') return [{ textContent: 'Не выведен' }];
      return [];
    },
  });

  const targetCheckboxes = targets.map((target, index) =>
    makeCheckbox(() => options.onTargetClick?.({ index, replaceRows, targetCheckboxes })),
  );
  rows = targets.map((target, index) => makeRow(target, targetCheckboxes[index]));

  function replaceRows(nextRows) {
    rows = nextRows;
  }

  const selectedCount = () => rows.reduce((count, row) => {
    const [checkbox] = row.querySelectorAll('input[type="checkbox"]');
    return count + (checkbox?.checked ? 1 : 0);
  }, 0);
  const action = {
    get textContent() { return `Вывести из оборота (${selectedCount()})`; },
    get disabled() { return selectedCount() === 0; },
    click() { dialogOpen = true; },
  };
  const table = {
    querySelectorAll(selector) {
      if (selector === 'tbody tr') return rows;
      if (selector === 'tbody input[type="checkbox"]:checked') {
        return rows
          .map(row => row.querySelectorAll('input[type="checkbox"]')[0])
          .filter(checkbox => checkbox?.checked);
      }
      return [];
    },
  };
  const page = {
    querySelectorAll(selector) {
      if (selector === 'input[type="date"]') return [{ value: '2026-09-18' }, { value: '2026-09-19' }];
      if (selector === 'table[aria-label="КИЗ для вывода из оборота"]') return [table];
      if (selector === 'button') return [action];
      return [];
    },
  };
  const dialog = { textContent: 'Выберите сертификат' };
  const document = {
    querySelector(selector) {
      if (selector === '[role="dialog"]') return dialogOpen ? dialog : null;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-testid="seller-kiz-withdrawal-page"]') return [page];
      if (selector === '[role="dialog"]') return dialogOpen ? [dialog] : [];
      return [];
    },
  };
  return {
    document,
    makeCheckbox,
    makeRow,
    replaceRows,
    get dialogOpen() { return dialogOpen; },
  };
}

function harnessWithRealDom(options = {}) {
  const previousDocument = global.document;
  const fakeDom = createFakeDom([EXPECTED[0]], options.dom);
  global.document = fakeDom.document;
  try {
    const h = harness({
      rows: [row(EXPECTED[0])],
      extraDeps: { ui: undefined, ...options.extraDeps },
    });
    return { ...h, fakeDom };
  } finally {
    global.document = previousDocument;
  }
}

function assertReadyDryRun(result, verifiedTargets) {
  assert.equal(result.status, 'ready');
  assert.equal(result.noSend, true);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes(TOKEN));
  // The result must report verified identities without prescribing its layout.
  for (const target of verifiedTargets) {
    for (const value of Object.values(target)) {
      assert.ok(serialized.includes(JSON.stringify(value)), `missing verified value for ${target.wb_order_id}`);
    }
  }
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

test('CI executes the full sold-KIZ helper contract', () => {
  const workflow = readFileSync(
    path.resolve(__dirname, '../../../.github/workflows/ci.yml'),
    'utf8',
  );
  assert.match(workflow, /avpack-sold-kiz-filter\.test\.cjs/);
});

test('default run is read-only and inspects only the first target, never all four', async () => {
  const h = harness();
  const result = await h.helper.run();
  assert.equal(h.mutations.length, 0);
  assert.deepEqual(h.calls.map(call => call.url.pathname), ['/api/auth/me', REGISTRY]);
  assert.equal(h.inspections.length, 1);
  assert.deepEqual(targetIdentity(h.inspections[0]), [EXPECTED[0]]);
  assertReadyDryRun(result, [EXPECTED[0]]);
});

test('explicit dry-run for multiple allowed orders never selects or opens anything', async () => {
  const h = harness();
  const result = await h.helper.run({ mode: 'dry-run', orderIds: EXPECTED.map(target => target.wb_order_id) });
  assert.equal(h.mutations.length, 0);
  assert.deepEqual(targetIdentity(h.inspections[0]), EXPECTED);
  assertReadyDryRun(result, EXPECTED);
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

test('execute selects exactly the requested verified targets and opens only the certificate dialog', async () => {
  const h = harness();
  const result = await h.helper.run({
    mode: 'execute',
    orderIds: [EXPECTED[2].wb_order_id, EXPECTED[0].wb_order_id],
  });
  assert.deepEqual(h.events, ['/api/auth/me', REGISTRY, 'inspect', 'selectAndOpen']);
  assert.equal(h.inspections.length, 1);
  assert.deepEqual(targetIdentity(h.inspections[0]), [EXPECTED[2], EXPECTED[0]]);
  assert.equal(h.mutations.length, 1);
  assert.deepEqual(targetIdentity(h.mutations[0]), [EXPECTED[2], EXPECTED[0]]);
  assert.equal(result.mode, 'execute');
  assert.equal(result.status, 'certificate_dialog_open');
  assert.equal(result.signed, false);
  assert.equal(result.sent, false);
  assert.deepEqual(targetIdentity(result.verifiedTargets), [EXPECTED[2], EXPECTED[0]]);
  assert.ok(!JSON.stringify(result).includes(TOKEN));
});

test('execute stops when the seller session changes before UI mutation', async () => {
  let reads = 0;
  const h = harness({ extraDeps: {
    storage: { getItem() { reads += 1; return reads === 1 ? TOKEN : 'changed-session'; } },
  } });
  await failsSafely(h, { mode: 'execute' });
  assert.equal(h.inspections.length, 1);
});

test('execute never selects after a failed UI preflight', async () => {
  const h = harness({ selection: { selectedCount: 1 } });
  await failsSafely(h, { mode: 'execute' });
  assert.equal(h.inspections.length, 1);
  assert.equal(h.mutations.length, 0);
});

test('execute surfaces a dialog-opening failure without retrying or signing', async () => {
  const h = harness({ extraDeps: {
    ui: {
      async inspectSelection() { return { selectedCount: 0, targetsReady: true }; },
      async selectAndOpen() { throw new Error('synthetic UI failure'); },
    },
  } });
  await failsSafely(h, { mode: 'execute' });
});

test('real DOM execute stops if the seller session changes after checkbox selection', async () => {
  let currentToken = TOKEN;
  const h = harnessWithRealDom({
    dom: { onTargetClick() { currentToken = 'changed-session'; } },
    extraDeps: { storage: { getItem() { return currentToken; } } },
  });
  await assert.rejects(() => h.helper.run({ mode: 'execute' }), /Сессия seller-кабинета изменилась/);
  assert.equal(h.fakeDom.dialogOpen, false);
});

test('real DOM execute rejects a same-count replacement with an unapproved checkbox', async () => {
  let fakeDom;
  const h = harnessWithRealDom({
    dom: {
      onTargetClick({ replaceRows }) {
        const unapproved = { row_id: 'other-row', wb_order_id: '9999999999', cis: 'unapproved-cis-value-that-is-long' };
        const checkbox = fakeDom.makeCheckbox();
        checkbox.checked = true;
        replaceRows([fakeDom.makeRow(unapproved, checkbox)]);
      },
    },
  });
  fakeDom = h.fakeDom;
  await assert.rejects(() => h.helper.run({ mode: 'execute' }), /Строки изменились|точное выделение/);
  assert.equal(h.fakeDom.dialogOpen, false);
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
  assertReadyDryRun(result, [EXPECTED[0]]);
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
