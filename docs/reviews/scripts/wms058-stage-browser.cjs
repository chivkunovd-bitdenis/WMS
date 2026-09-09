// WMS-058 one-off actual staging QA. Run only after root confirms deployed SHA.
// No mocks, installs, DB access, external shipment, or manual stock restoration.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const WEB = 'https://web-production-9e7c1.up.railway.app';
const MP = '/operations/marketplace-unload-requests';
const TENANT = '9c31f3f4-ce62-4c1f-891a-295b278f1e69';
const SELLER = '50110328-fa03-4604-b2e4-8ca27fc8bb41';
const WAREHOUSE = '307c0ccd-9a6b-41df-9180-f8ed68022237';
const PRODUCT = '45587c50-451f-4d0a-b233-98c07be4dc9d';
const BARCODE = '2000000000013';
const SOURCE = '817b4384-17ba-4872-9a81-d8f62adc3dfe';
const SOURCE_CODE = 'FBSVID-BOX-03';
const LOCATION = '43a2a23a-0653-49de-82f5-b60f2ba48530';
const SORTING = 'fb46f84c-252c-4e72-9a76-8136dfd549ff';
const own = new Set();
const evidence = { started: new Date().toISOString(), steps: [], blocked: [], pageErrors: [], cleanup: [], inb: 'Skipped: no separately owned persisted INB fixture identified in reports.' };
let token;
function permit(path, method, create = false) {
  if (method === 'GET') return true;
  if (create && method === 'POST' && path === MP) return true;
  return [...own].some(id => path.startsWith(`${MP}/${id}/`) &&
    (path === `${MP}/${id}/lines` || path === `${MP}/${id}/confirm` ||
     path === `${MP}/${id}/cancel` || path === `${MP}/${id}/boxes` ||
     path === `${MP}/${id}/pick/scan` ||
     new RegExp(`^${MP}/${id}/boxes/[^/]+/scan$`).test(path)));
}
async function api(path, method = 'GET', body, create = false) {
  assert(permit(path.split('?')[0], method, create), `Unowned mutation: ${method} ${path}`);
  const r = await fetch(`${WEB}/api${path}`, {
    method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await r.json();
  assert(r.ok, `${method} ${path}: HTTP ${r.status} ${JSON.stringify(data)}`);
  return data;
}
async function physical() {
  const balances = await Promise.all([LOCATION, SORTING].map(async location => ({
    location, row: (await api(`/operations/inventory-balances?storage_location_id=${location}`)).find(x => x.product_id === PRODUCT) ?? null,
  })));
  const movements = (await api('/operations/inventory-movements?limit=500')).filter(x => x.product_id === PRODUCT);
  return { balances, movements };
}
async function snapshot(id, name) {
  const detail = await api(`${MP}/${id}`);
  assert.equal(detail.seller_id, SELLER);
  assert.equal(detail.warehouse_id, WAREHOUSE);
  const option = (await api(`${MP}/${id}/pick-options`)).find(x => x.product_id === PRODUCT);
  assert(option);
  const state = { name, detail, option, ...(await physical()) };
  evidence.steps.push(state);
  return state;
}
function sources(state) {
  return Object.fromEntries(state.option.locations.flatMap(loc => loc.sources.map(src => [
    `${loc.storage_location_id}/${src.is_loose ? 'loose' : src.container_path.at(-1).id}`,
    src.quantity,
  ])));
}
function movementIds(state) { return state.movements.map(x => x.id).sort(); }
function assertSourceDelta(before, after, delta) {
  const expected = sources(before);
  expected[`${LOCATION}/${SOURCE}`] += delta;
  assert.deepEqual(sources(after), expected, 'Exact source balances changed unexpectedly');
}
async function openBox(page, id, boxId) {
  await page.goto(`${WEB}/ff/mp-shipments?open_mp=${id}`);
  await page.getByRole('tab', { name: /^Упаковка/ }).click();
  const fill = page.getByTestId(`ff-mp-box-add-products-${boxId}`);
  if (!await fill.isVisible()) await page.getByText('Короба', { exact: true }).click();
  await fill.click();
  await page.getByTestId(`ff-mp-box-add-row-${PRODUCT}`).waitFor();
}
async function scan(page, id, boxId, barcode, expectedCount) {
  const input = page.getByTestId('ff-mp-box-add-scan-input');
  const start = await page.evaluate(() => performance.now());
  const pending = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`${MP}/${id}/boxes/${boxId}/scan`));
  await input.fill(barcode);
  await input.press('Enter');
  const response = await pending;
  const data = await response.json();
  assert.equal(response.status(), 200, `Scan response: ${JSON.stringify(data)}`);
  if (barcode === SOURCE_CODE) {
    assert.equal(data.kind, 'container');
    assert.equal(data.container_id, SOURCE);
    assert.equal(data.storage_location_id, LOCATION);
    await page.getByTestId('ff-mp-box-add-active-location').filter({ hasText: SOURCE_CODE }).waitFor();
  } else {
    await page.waitForFunction(({ pid, count }) => document.querySelector(`[data-testid="ff-mp-box-add-row-${pid}"]`)?.querySelectorAll('td')[4]?.textContent === String(count), { pid: PRODUCT, count: expectedCount });
  }
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await response.finished();
  evidence.steps.push({ name: `browser scan ${barcode}`, response: data,
    visible: await page.getByTestId(`ff-mp-box-add-row-${PRODUCT}`).innerText(),
    screenMs: (await page.evaluate(() => performance.now())) - start,
    httpMs: response.request().timing().responseEnd });
}
async function main() {
  assert.equal(process.argv[2], '--execute-after-root-ready', 'Preparation only: explicit root deployment-ready required');
  assert(/^[0-9a-f]{40}$/.test(process.argv[3] ?? ''), 'Record root-confirmed deployed full SHA');
  evidence.rootConfirmedDeployedSha = process.argv[3];
  const output = process.argv[4];
  assert(output && output.startsWith('/') && output.endsWith('.json'), 'Absolute .json evidence output path required');
  token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt', 'utf8').trim().replace(/^Bearer\s+/i, '');
  let browser;
  try {
    const me = await api('/auth/me');
    assert.equal(me.tenant_id, TENANT);
    assert.equal(me.role, 'fulfillment_admin');
    const products = await api('/products');
    const product = products.find(x => x.id === PRODUCT);
    assert(product && product.seller_id === SELLER && product.sku_code === 'EMU-KIZ-OPTIONAL');
    const available = (await api(`${MP}/available-products?warehouse_id=${WAREHOUSE}&seller_id=${SELLER}`)).find(x => x.product_id === PRODUCT);
    assert(available?.available >= 2, 'Insufficient QA availability');
    evidence.before = await physical();
    const doc = await api(MP, 'POST', { warehouse_id: WAREHOUSE, seller_id: SELLER, wb_mp_warehouse_id: 507 }, true);
    own.add(doc.id);
    evidence.document = doc;
    await api(`${MP}/${doc.id}/lines`, 'POST', { product_id: PRODUCT, quantity: 2 });
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    await api(`${MP}/${doc.id}/confirm`, 'POST', { planned_shipment_date: tomorrow });
    const box = await api(`${MP}/${doc.id}/boxes`, 'POST', { box_preset: '60_40_40' });
    evidence.box = box;
    const initial = await snapshot(doc.id, 'confirmed before source scan');
    const source = initial.option.locations.find(x => x.storage_location_id === LOCATION)?.sources.find(x => x.container_path.at(-1)?.id === SOURCE);
    assert(source && source.quantity >= 2 && source.available >= 2, 'Known QA box unavailable; do not choose another source');
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(value => localStorage.setItem('wms_token_ff', value), token);
    await context.route('**/*', async route => {
      const req = route.request();
      const url = new URL(req.url());
      if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method()) &&
          (url.origin !== WEB || !url.pathname.startsWith('/api/') || !permit(url.pathname.slice(4), req.method()))) {
        evidence.blocked.push({ method: req.method(), path: url.pathname });
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => evidence.pageErrors.push(error.message));
    await openBox(page, doc.id, box.id);
    await scan(page, doc.id, box.id, SOURCE_CODE);
    const selected = await snapshot(doc.id, 'source selected');
    assertSourceDelta(initial, selected, 0);
    assert.deepEqual(movementIds(selected), movementIds(initial));
    await scan(page, doc.id, box.id, BARCODE, 1);
    const first = await snapshot(doc.id, 'one scanned into box');
    assertSourceDelta(selected, first, -1);
    assert.equal(first.option.picked_qty, 1);
    assert.equal(first.option.boxed_qty, 1);
    await page.getByTestId('ff-mp-box-add-dialog').getByRole('button', { name: 'Закрыть', exact: true }).click();
    await api(`${MP}/${doc.id}/pick/scan`, 'POST', { barcode: BARCODE, storage_location_id: LOCATION, container_kind: 'box', container_id: SOURCE });
    const picked = await snapshot(doc.id, 'second unit already picked by public API');
    assertSourceDelta(first, picked, -1);
    assert.equal(picked.option.picked_qty, 2);
    assert.equal(picked.option.boxed_qty, 1);
    await openBox(page, doc.id, box.id);
    await scan(page, doc.id, box.id, BARCODE, 2);
    const placed = await snapshot(doc.id, 'already picked unit placed through browser');
    assertSourceDelta(picked, placed, 0);
    assert.deepEqual(movementIds(placed), movementIds(picked));
    assert.equal(placed.option.picked_qty, 2);
    assert.equal(placed.option.boxed_qty, 2);
    await page.screenshot({ path: output.replace(/\.json$/, '.png'), fullPage: false });
    evidence.result = 'passed';
  } catch (error) {
    evidence.result = 'failed';
    evidence.error = error.message;
    process.exitCode = 1;
  } finally {
    if (browser) {
      try { await browser.close(); }
      catch (error) { evidence.cleanup.push({ browserCloseError: error.message }); process.exitCode = 1; }
    }
    for (const id of own) {
      try {
        await api(`${MP}/${id}/cancel`, 'POST', {});
        const doc = await api(`${MP}/${id}`);
        evidence.cleanup.push({ id, status: doc.status });
        assert.equal(doc.status, 'cancelled');
      } catch (error) { evidence.cleanup.push({ id, error: error.message }); process.exitCode = 1; }
    }
    try { evidence.afterCleanup = await physical(); } catch (error) { evidence.cleanup.push({ readError: error.message }); }
    token = undefined;
    fs.writeFileSync(output, JSON.stringify(evidence, null, 2));
    process.stdout.write(JSON.stringify({ result: evidence.result, error: evidence.error, documents: [...own], cleanup: evidence.cleanup, evidence: output }) + '\n');
  }
}
main().catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
