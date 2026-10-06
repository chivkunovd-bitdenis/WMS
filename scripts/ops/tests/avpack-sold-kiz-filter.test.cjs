'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createHelper, TARGET_ROW_IDS } = require('../avpack-sold-kiz-filter.js');

const TENANT = 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe';
const SELLER = '0b8da5d8-f43a-42f5-a2ec-43173ea844bd';
const TOKEN = 'synthetic-token-never-return';
const ORIGIN = 'https://wms.sellerfocus.pro';
const REGISTRY = '/api/operations/marking-codes/self/withdrawals';
const EXPECTED_IDS = [
  '076e540e-a663-4b4e-acac-c76f1bc32b47', '0d2b2f9f-799c-476c-b4f8-8090efff5ddb',
  '1448adff-ab8f-4b98-bb93-ff1c94884354', '16ac02f7-d28c-4ad7-a2d1-1de398b91b10',
  '194cec2f-a1fe-455f-adea-8c18c47af7c4', '1b7364c8-3cd5-4df2-8f82-6d5920686b67',
  '1d31f59a-61c1-44fe-aabf-d8fed9393f22', '20765aea-1118-41c0-83b2-539747460d80',
  '2203a0ff-70fd-4bc5-a1dd-cf2e2b99f865', '249ccc60-7b88-4c4f-9951-1645943d62d2',
  '2797064e-6eb8-4591-9f10-b8c158d78573', '2a711328-07d8-4d18-98b3-de5d5286cb8e',
  '2d7f9070-3296-4e0a-9b37-f9caa732fa64', '2dc9344b-0445-43e6-a142-703018d48631',
  '2f47bddf-0f62-453c-a90f-4b016c9ccea0', '3bb90f51-e57b-4d62-858f-f9893e4700cf',
  '3db6a144-c80d-4ffe-82ff-48fd464c9b9e', '4c2424e6-8694-4ce8-a4ae-bf8c26ff12f5',
  '4e7d9860-af10-4e94-ac80-69d477cf4732', '5358c1aa-8ec1-45b6-8575-c5929eaa1a50',
  '5ace981a-716f-4776-80cf-4e7d3a5e964a', '5f2ab33c-8977-4004-b933-cc9e659f081a',
  '61ccae09-7fba-4d12-b07a-64f77199e888', '654d84c2-2e3b-4666-81d8-1d3de30a5ddf',
  '677a666e-bc7a-454b-8854-b54db56e0773', '68b5caae-b6f4-4551-8fd4-5c582cd67861',
  '6990f114-490f-4c26-9e27-9c2a01d68535', '6c5b9ad3-d9d9-47af-a62e-5fe00cdde91a',
  '7389967b-1e87-4b66-9797-c9d641b99e9f', '76dbb4e8-a225-4b9e-ac26-3263dd4eaef3',
  '795de647-69e7-402f-aef7-d94686d21181', '79ea2e70-afc8-4ac4-a778-b6271f9f2ef8',
  '7c8880ee-fe16-43c0-9db5-47dda2c3a5e0', '81892e40-c34f-4417-bbc1-c85688454ae8',
  '81a42d48-6231-466a-98c8-480f07ca0eb8', '895b16d1-0b18-4e88-9a40-7ef5f3c2bf3c',
  '8a55696a-0cd5-4325-af2b-50500acb2cfc', '8cb4ac19-699b-4ff1-aa94-53c6e790874e',
  '8f174987-f7cf-4f23-99f3-63ef54584a97', '924d6a02-b1a9-49ce-9fe2-095d9339209f',
  '943280fe-2324-42cf-8d48-f3eeb2d472a3', '9680c1e7-45c7-4199-a31f-4166c2e8ba5c',
  '9cfeb72a-197c-41cf-9402-89792a729d8e', '9d2c7535-e3e7-4228-a155-06de1143cc3e',
  '9d8b62f7-f9ec-4858-b4a2-be425058228e', 'a61f1b1a-8c0a-4e56-b078-60fad85a5359',
  'a6d27c01-1453-4815-9c20-70e0e3077873', 'a7e9b9a5-55f9-4814-b035-2305f3fbec99',
  'a83a66e7-78bb-4ec5-9324-80ca9cf31dba', 'ab8be18b-bee1-4c36-b8a9-5391ead3ec28',
  'aee615ad-5bdd-49c3-8df4-26f3984f7d63', 'b0b78a7a-db22-4716-90ae-0a1e3c43a58d',
  'b8489102-34ac-460e-8cbf-b51a2f66f3ee', 'bfb5e4ff-dbfb-406e-b81a-0c03c6ca9a6b',
  'c03394b0-6264-491c-8b99-6ec5ca5c7174', 'c1716e47-e2e3-490f-bbf8-e1291558a824',
  'c215df68-78de-4dcf-82ab-7788d8e3b419', 'c5219133-721a-41b3-b6a4-093c575daeeb',
  'c9391ebe-21f5-4b1a-89c4-1607563e341a', 'cc5e2db9-eef5-4f0a-88e4-237c9add2b15',
  'cda5fad8-0b4b-48e1-98dd-23a46216853d', 'cecbc538-7c28-47a8-8c38-52d1dbae1b5e',
  'd4265905-b9fe-4366-b979-7071d54ded6a', 'd4b5f1a2-e4be-49db-9e3d-dff90107dbad',
  'd713c7eb-4ef7-472e-95de-794400536b0e', 'd79b900c-7bdb-4cbf-840c-3abe6efb9299',
  'd92b6072-c1e3-4fe7-9243-1d6f2d6b35ee', 'dcf8853c-c496-40f3-828c-79268e671887',
  'e03e5e9b-2e8a-49bf-9c4b-f820ee14c559', 'e324a9e0-0d68-42ba-a423-61afebe28378',
  'e3900a60-ddc1-4d65-8496-34cb9b51e186', 'e690a619-15aa-4675-8610-969751142d7a',
  'ea17ae7f-1470-46d8-85cf-ca495c5bb554', 'ee3f9ce2-515b-4141-9b8a-03220b45b317',
  'f149cee5-b6d7-4f6a-964a-dfb7f2930e04', 'f5bedf17-4c1c-4cd1-a8ef-27409af61b48',
  'f8c488e6-d6b8-464b-86c6-9d25d6b1e87b', 'fb8b5faf-cbcb-4f84-a95e-600064a938f3',
  'fca14802-f8cd-4221-9f62-e853d8bfaedf', 'fd2599f8-acd7-4207-a3f0-fdc3ede7d3dc',
];

const targetRow = (rowId) => ({
  row_id: rowId,
  status: 'not_withdrawn',
  operation_id: null,
  wb_order_id: `wb-${rowId}`,
  cis: `cis-${rowId}`,
});

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function harness(options = {}) {
  const calls = [];
  const events = [];
  let token = TOKEN;
  const identity = {
    tenant_id: TENANT,
    seller_id: SELLER,
    active_seller_id: SELLER,
    role: 'fulfillment_seller',
    withdrawal_enabled: true,
    ...options.identity,
  };
  const registryRows = options.rows ?? [
    ...Array.from({ length: 190 }, (_, index) => targetRow(`unrelated-${index}`)),
    ...EXPECTED_IDS.map(targetRow),
  ];
  const root = {
    location: { origin: ORIGIN, pathname: '/seller/honest-sign/withdrawals', ...options.location },
    localStorage: { getItem: () => token },
    Response,
  };
  const originalFetch = async (input, init = {}) => {
    const url = new URL(String(input), ORIGIN);
    const method = String(init.method ?? 'GET').toUpperCase();
    calls.push({ url, method, init });
    if (url.pathname === '/api/auth/me') return response(identity);
    if (url.pathname === REGISTRY && method === 'GET') {
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '50');
      return response({ rows: registryRows.slice(offset, offset + limit), total: registryRows.length });
    }
    return response({ passthrough: true }, 202);
  };
  root.fetch = originalFetch;
  const ui = {
    async inspectSelection() {
      events.push('inspect');
      return { selectedCount: options.selectedCount ?? 0 };
    },
    async refreshSelectAllAndOpen(expectedCount) {
      events.push('open');
      const page = await root.fetch(`${REGISTRY}?limit=250&offset=0&search=anything`);
      const body = await page.json();
      assert.equal(body.total, expectedCount);
      assert.deepEqual(body.rows.map(row => row.row_id), EXPECTED_IDS);
      if (options.changeTokenInUi) token = 'changed-token';
      return { selectedCount: expectedCount, dialogOpen: true };
    },
    async rollbackPreparation() {
      events.push('rollback');
    },
  };
  const helper = createHelper({ root, ui });
  return { helper, root, calls, events, originalFetch, setToken(value) { token = value; } };
}

test('the frozen production snapshot contains exactly the 80 sold row ids', () => {
  assert.deepEqual([...TARGET_ROW_IDS], EXPECTED_IDS);
  assert.equal(new Set(TARGET_ROW_IDS).size, 80);
});

test('dry-run verifies all pages but does not replace fetch or mutate the UI', async () => {
  const h = harness();
  const result = await h.helper.run({ mode: 'dry-run' });
  assert.equal(result.status, 'ready');
  assert.equal(result.targetCount, 80);
  assert.equal(result.noSend, true);
  assert.equal(h.root.fetch, h.originalFetch);
  assert.deepEqual(h.events, ['inspect']);
  assert.deepEqual(
    h.calls.filter(call => call.url.pathname === REGISTRY).map(call => call.url.searchParams.get('offset')),
    ['0', '250'],
  );
  assert.ok(!JSON.stringify(result).includes(TOKEN));
});

test('execute exposes only the exact 80 rows to the existing UI and opens its certificate dialog', async () => {
  const h = harness();
  const result = await h.helper.run({ mode: 'execute' });
  assert.equal(result.status, 'certificate_dialog_open');
  assert.equal(result.targetCount, 80);
  assert.equal(result.signed, false);
  assert.equal(result.sent, false);
  assert.equal(result.noSend, true);
  assert.ok(h.calls.every(call => call.method === 'GET'), 'preparation cannot sign or submit an operation');
  assert.ok(h.calls.every(call => ['/api/auth/me', REGISTRY].includes(call.url.pathname)));
  assert.notEqual(h.root.fetch, h.originalFetch);
  assert.deepEqual(h.events, ['inspect', 'open']);
});

test('the temporary filter never intercepts POST or operation URLs', async () => {
  const h = harness();
  await h.helper.run({ mode: 'execute' });
  const post = await h.root.fetch(`${REGISTRY}/operations`, { method: 'POST', body: '{}' });
  assert.equal(post.status, 202);
  assert.equal(h.root.fetch, h.originalFetch, 'the first operation POST must remove the stale registry filter');
  const operationCalls = h.calls.filter(call => call.url.pathname.endsWith('/operations'));
  assert.equal(operationCalls.length, 1);
  assert.equal(operationCalls[0].method, 'POST');
});

for (const [name, mutate] of [
  ['one sold row is missing', rows => rows.filter(row => row.row_id !== EXPECTED_IDS[0])],
  ['one sold row is duplicated', rows => [...rows, targetRow(EXPECTED_IDS[0])]],
  ['one sold row already has an operation', rows => rows.map(row => row.row_id === EXPECTED_IDS[0] ? { ...row, operation_id: 'op' } : row)],
  ['one sold row is already withdrawn', rows => rows.map(row => row.row_id === EXPECTED_IDS[0] ? { ...row, status: 'withdrawn' } : row)],
]) {
  test(`${name} aborts before installing the filter`, async () => {
    const base = [...Array.from({ length: 190 }, (_, index) => targetRow(`unrelated-${index}`)), ...EXPECTED_IDS.map(targetRow)];
    const h = harness({ rows: mutate(base) });
    await assert.rejects(() => h.helper.run({ mode: 'execute' }));
    assert.equal(h.root.fetch, h.originalFetch);
    assert.ok(!String((await h.helper.run({ mode: 'dry-run' }).catch(error => error)).stack).includes(TOKEN));
  });
}

test('preexisting selection aborts before installing the filter', async () => {
  const h = harness({ selectedCount: 1 });
  await assert.rejects(() => h.helper.run({ mode: 'execute' }), /выбран/i);
  assert.equal(h.root.fetch, h.originalFetch);
});

for (const [field, value] of [
  ['tenant_id', 'wrong'], ['seller_id', 'wrong'], ['active_seller_id', 'wrong'],
  ['role', 'fulfillment_admin'], ['withdrawal_enabled', false],
]) {
  test(`identity mismatch in ${field} aborts before reading the sold registry`, async () => {
    const h = harness({ identity: { [field]: value } });
    await assert.rejects(() => h.helper.run({ mode: 'execute' }), /AVpack|seller|селлер/i);
    assert.equal(h.root.fetch, h.originalFetch);
    assert.deepEqual(h.calls.map(call => call.url.pathname), ['/api/auth/me']);
    assert.deepEqual(h.events, []);
  });
}

test('session change while the UI is being prepared restores original fetch', async () => {
  const h = harness({ changeTokenInUi: true });
  await assert.rejects(() => h.helper.run({ mode: 'execute' }), /сесси/i);
  assert.equal(h.root.fetch, h.originalFetch);
  assert.deepEqual(h.events, ['inspect', 'open', 'rollback']);
});

test('session change after successful preparation restores the original transport', async () => {
  const h = harness();
  await h.helper.run({ mode: 'execute' });
  h.setToken('changed-token');
  await assert.rejects(() => h.root.fetch(`${REGISTRY}?limit=50&offset=0`), /сесси/i);
  assert.equal(h.root.fetch, h.originalFetch);
});

test('logout after successful preparation also restores the original transport', async () => {
  const h = harness();
  await h.helper.run({ mode: 'execute' });
  h.setToken(null);
  await assert.rejects(() => h.root.fetch(`${REGISTRY}?limit=50&offset=0`), /Войдите|сесси/i);
  assert.equal(h.root.fetch, h.originalFetch);
});

test('a second helper cannot accept the already installed snapshot as backend truth', async () => {
  const h = harness();
  await h.helper.run({ mode: 'execute' });
  assert.throws(() => createHelper({ root: h.root, ui: { inspectSelection() {} } }), /уже установлен|перезагруз/i);
});

for (const location of [
  { origin: 'https://sellerfocus.pro' },
  { origin: 'https://wrong.example' },
  { origin: 'https://wms.sellerfocus.pro.evil.test' },
  { origin: 'http://wms.sellerfocus.pro' },
  { pathname: '/seller/orders' },
]) {
  test(`wrong sold registry origin or route aborts before network or UI: ${JSON.stringify(location)}`, async () => {
    const h = harness({ location });
    await assert.rejects(() => h.helper.run({ mode: 'execute' }));
    assert.equal(h.calls.length, 0);
    assert.deepEqual(h.events, []);
    assert.equal(h.root.fetch, h.originalFetch);
  });
}
