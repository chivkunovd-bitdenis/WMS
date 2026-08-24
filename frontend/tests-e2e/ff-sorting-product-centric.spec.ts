import { test, expect, type Locator, type Page } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { beginInboundReceiving } from './inbound-boxes-helpers';

async function selectSortingLocation(page: Page, row: Locator, name: RegExp): Promise<void> {
  await row.getByTestId('ff-sorting-cell-location').getByRole('combobox').click();
  await page.getByRole('option', { name }).click();
}

// TC-NEW-SORT-01 — box contents stay under the box; only loose goods remain below.
test('ff sorting: box product rows and loose goods are separate', async ({ page }) => {
  const email = `e2e-sort-mix-${Date.now()}@example.com`;
  const sku = `SKU-SORT-MIX-${Date.now()}`;
  const whCode = `wh-sort-mix-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort Mix');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;

  const locLoose = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'LOOSE-1' },
  });
  const locBox = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'BOX-1' },
  });
  expect(locLoose.ok()).toBeTruthy();
  expect(locBox.ok()).toBeTruthy();

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 10 },
  });
  await page.request.post(`${base}/${rid}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, rid);

  const doc = await page.request.get(`${base}/${rid}`, { headers: h });
  expect(doc.ok()).toBeTruthy();
  const lineId = ((await doc.json()) as { lines: { id: string }[] }).lines[0]!.id;

  const boxRes = await page.request.post(`${base}/${rid}/boxes`, { headers: h });
  expect(boxRes.ok()).toBeTruthy();
  const box = (await boxRes.json()) as { id: string; box_number: number };
  const boxId = box.id;
  const putBox = await page.request.put(`${base}/${rid}/boxes/${boxId}/lines/${pid}`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { quantity: 6 },
  });
  expect(putBox.ok()).toBeTruthy();
  const patchLoose = await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 4 },
  });
  expect(patchLoose.ok()).toBeTruthy();

  const complete = await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });
  expect(complete.ok()).toBeTruthy();

  await page.goto('/app/ff/sorting');
  const [distributionRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.getByTestId('ff-inbound-queue-row').first().click(),
  ]);
  expect(distributionRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();
  const boxRow = page.getByTestId('ff-sorting-box-putaway-row').filter({ hasText: `Короб №${box.box_number}` });
  await expect(boxRow).toBeVisible();
  await expect(boxRow.getByTestId('ff-sorting-box-product-row')).toHaveCount(1);
  await expect(boxRow.getByTestId('ff-sorting-box-product-sku')).toHaveText(sku);
  await expect(boxRow.getByTestId('ff-sorting-box-product-qty')).toHaveText('6');
  await expect(boxRow.getByTestId('ff-sorting-cell-location')).toHaveCount(0);

  const productCard = page.getByTestId('ff-sorting-product-card').first();
  await expect(productCard.getByTestId('ff-sorting-product-accepted')).toHaveText('4');
  await expect(productCard.getByTestId('ff-sorting-cell-row')).toHaveCount(1);
  await expect(productCard).not.toContainText('Короб №');
  await page.screenshot({
    path: '../docs/evidence/20260824-box-contents-sorting/box-and-loose.png',
    fullPage: true,
  });

  await boxRow.getByTestId('ff-sorting-box-location').getByRole('combobox').click();
  await page.getByRole('option', { name: 'BOX-1' }).click();
  await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'POST' && r.url().includes(`/boxes/${boxId}/putaway`) && r.ok(),
    ),
    boxRow.getByTestId('ff-sorting-box-putaway-submit').click(),
  ]);
  await expect(page.getByTestId('ff-sorting-box-putaway-row')).toHaveCount(0);

  const looseRow = page.getByTestId('ff-sorting-product-card').first().getByTestId('ff-sorting-cell-row').first();
  await selectSortingLocation(page, looseRow, /LOOSE-1/);
  await looseRow.getByTestId('ff-sorting-cell-qty').fill('4');
  await expect(page.getByTestId('ff-sorting-save')).toHaveCount(0);
  await expect(page.getByTestId('ff-sorting-apply')).toBeEnabled();

  await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'PUT' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.waitForResponse(
      (r) => r.request().method() === 'POST' && r.url().includes('/distribution-complete') && r.ok(),
    ),
    page.getByTestId('ff-sorting-apply').click(),
  ]);

  await page.reload();
  await expect(page.getByTestId('ff-inbound-queue-empty')).toContainText('Нет приёмок в сортировке');

  const distributionReadback = await page.request.get(`${base}/${rid}/distribution-lines`, { headers: h });
  expect(distributionReadback.ok()).toBeTruthy();
  const distributionRows = (await distributionReadback.json()) as {
    box_id: string | null;
    storage_location_code: string;
    quantity: number;
  }[];
  expect(distributionRows).toEqual(expect.arrayContaining([
    expect.objectContaining({ box_id: boxId, storage_location_code: 'BOX-1', quantity: 6 }),
    expect.objectContaining({ box_id: null, storage_location_code: 'LOOSE-1', quantity: 4 }),
  ]));
});

// TC-REV-SORT-FE-02 — failed GET distribution-lines shows error and blocks apply.
test('ff sorting: failed distribution-lines load shows error and blocks apply', async ({ page }) => {
  const email = `e2e-sort-fail-${Date.now()}@example.com`;
  const sku = `SKU-SORT-FAIL-${Date.now()}`;
  const whCode = `wh-sort-fail-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort Fail');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;

  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'CELL-A' },
  });
  expect(loc.ok()).toBeTruthy();
  const locBody = (await loc.json()) as { id: string };

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 5 },
  });
  await page.request.post(`${base}/${rid}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, rid);

  const doc = await page.request.get(`${base}/${rid}`, { headers: h });
  expect(doc.ok()).toBeTruthy();
  const lineId = ((await doc.json()) as { lines: { id: string }[] }).lines[0]!.id;

  const patchActual = await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 5 },
  });
  expect(patchActual.ok()).toBeTruthy();

  const complete = await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });
  expect(complete.ok()).toBeTruthy();

  await page.goto('/app/ff/sorting');
  const [distributionRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.getByTestId('ff-inbound-queue-row').first().click(),
  ]);
  expect(distributionRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  const productCard = page.getByTestId('ff-sorting-product-card').first();
  await expect(productCard.getByTestId('ff-sorting-cell-row')).toHaveCount(1);
  const row = productCard.getByTestId('ff-sorting-cell-row').first();
  await selectSortingLocation(page, row, /CELL-A/);
  await row.getByTestId('ff-sorting-cell-qty').fill('5');
  await expect(page.getByTestId('ff-sorting-save')).toHaveCount(0);

  const seedDistribution = await page.request.put(`${base}/${rid}/distribution-lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: [
      {
        box_id: null,
        product_id: pid,
        storage_location_id: locBody.id,
        quantity: 5,
      },
    ],
  });
  expect(seedDistribution.ok()).toBeTruthy();
  await page.goto('/app/ff/sorting');

  await page.route('**/distribution-lines', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'distribution load failed' }),
      });
      return;
    }
    await route.continue();
  });

  await page.reload();
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'GET' &&
        r.url().includes('/distribution-lines') &&
        r.status() === 500,
    ),
    page.getByTestId('ff-inbound-queue-row').first().click(),
  ]);

  await expect(page.getByTestId('ff-sorting-distribution-load-error')).toBeVisible();
  await expect(page.getByTestId('ff-sorting-distribution-retry')).toBeVisible();
  await expect(page.getByTestId('ff-sorting-save')).toHaveCount(0);
  await expect(page.getByTestId('ff-sorting-apply')).toBeDisabled();

  const putPromise = page.waitForRequest(
    (req) => req.method() === 'PUT' && req.url().includes('/distribution-lines'),
    { timeout: 1500 },
  );
  await page.getByTestId('ff-sorting-apply').click({ force: true }).catch(() => undefined);
  await expect(putPromise).rejects.toThrow();
});

// TC-NEW-SORT-03 — scanner-first cell -> product -> +1, apply locks the document and closes the sorting balance.
test('ff sorting scanner-first: cell barcode then product scans apply distribution', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const email = `e2e-sort-scan-${Date.now()}@example.com`;
  const sku = `SKU-SORT-SCAN-${Date.now()}`;
  const whCode = `wh-sort-scan-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort Scan');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;
  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'SCAN-A-01' },
  });
  expect(loc.ok()).toBeTruthy();
  const locBody = (await loc.json()) as { id: string; barcode: string };

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Сканируемый длинный товар для сортировки', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  const line = await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 2 },
  });
  const lineId = ((await line.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, rid);
  await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 2 },
  });
  await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });

  await page.goto('/app/ff/sorting');
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-queue-status').first()).toContainText('В сортировке');
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  const scanInput = page.getByTestId('ff-sorting-scan-input');
  await scanInput.fill(locBody.barcode);
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/distribution-scan') && r.ok()),
    scanInput.press('Enter'),
  ]);
  await expect(page.getByTestId('ff-sorting-scan-message')).toContainText('Активная ячейка: SCAN-A-01');
  await expect(scanInput).toBeFocused();

  await scanInput.fill(`UNKNOWN-SORT-${Date.now()}`);
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/distribution-scan')),
    scanInput.press('Enter'),
  ]);
  await expect(page.getByTestId('ff-sorting-error')).toContainText('Такой товар или ячейка не найдены');
  await expect(scanInput).toHaveValue('');
  await expect(scanInput).toBeFocused();

  for (const expected of ['разложено 1, осталось 1', 'разложено 2, осталось 0']) {
    await scanInput.fill(sku);
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/distribution-scan') && r.ok()),
      scanInput.press('Enter'),
    ]);
    await expect(page.getByTestId('ff-sorting-scan-message')).toContainText(expected);
  }

  const card = page.getByTestId('ff-sorting-product-card').first();
  await expect(card.getByTestId('ff-sorting-product-distributed')).toHaveText('2');
  await expect(card.getByTestId('ff-sorting-product-remaining')).toHaveText('0');

  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/distribution-complete') && r.ok()),
    page.getByTestId('ff-sorting-apply').click(),
  ]);
  await expect(page.getByTestId('ff-sorting-posted-done')).toBeVisible();
  await expect(page.getByTestId('ff-sorting-all-done')).toBeVisible();

  const balances = await page.request.get('/api/operations/inventory-balances/summary', { headers: h });
  const row = ((await balances.json()) as { product_id: string; quantity_in_sorting: number; quantity_in_storage: number }[])
    .find((item) => item.product_id === pid);
  expect(row).toMatchObject({ quantity_in_sorting: 0, quantity_in_storage: 2 });
});

// TC-URG-SORT-BOX-01 — scan box -> cell places every SKU; second box is placed manually.
test('ff sorting: whole boxes go to one cell by scan or one explicit row action', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const suffix = String(Date.now());
  const email = `e2e-whole-box-${suffix}@example.com`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Whole Box');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const warehouse = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад коробов', code: `whole-box-${suffix}` },
  });
  expect(warehouse.ok()).toBeTruthy();
  const warehouseId = ((await warehouse.json()) as { id: string }).id;
  const scanLocationRes = await page.request.post(`/api/warehouses/${warehouseId}/locations`, {
    headers: h,
    data: { code: 'SCAN-BOX-A-01' },
  });
  const manualLocationRes = await page.request.post(`/api/warehouses/${warehouseId}/locations`, {
    headers: h,
    data: { code: 'MANUAL-BOX-A-02' },
  });
  expect(scanLocationRes.ok()).toBeTruthy();
  expect(manualLocationRes.ok()).toBeTruthy();
  const scanLocation = (await scanLocationRes.json()) as { id: string; barcode: string };
  const manualLocation = (await manualLocationRes.json()) as { id: string; barcode: string };

  const products: { id: string; qty: number }[] = [];
  for (const [index, qty] of [[1, 2], [2, 3], [3, 4]] as const) {
    const product = await page.request.post('/api/products', {
      headers: h,
      data: {
        name: `Товар короба ${index}`,
        sku_code: `WHOLE-BOX-${index}-${suffix}`,
        length_mm: 10,
        width_mm: 10,
        height_mm: 10,
      },
    });
    expect(product.ok()).toBeTruthy();
    products.push({ id: ((await product.json()) as { id: string }).id, qty });
  }

  const base = '/api/operations/inbound-intake-requests';
  const request = await page.request.post(base, {
    headers: h,
    data: { warehouse_id: warehouseId },
  });
  expect(request.ok()).toBeTruthy();
  const requestId = ((await request.json()) as { id: string }).id;
  for (const product of products) {
    const line = await page.request.post(`${base}/${requestId}/lines`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { product_id: product.id, expected_qty: product.qty },
    });
    expect(line.ok()).toBeTruthy();
  }
  await page.request.post(`${base}/${requestId}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, requestId);

  const createFilledBox = async (contents: { id: string; qty: number }[]) => {
    const boxResponse = await page.request.post(`${base}/${requestId}/boxes`, { headers: h });
    expect(boxResponse.ok()).toBeTruthy();
    const box = (await boxResponse.json()) as {
      id: string;
      box_number: number;
      internal_barcode: string;
    };
    for (const product of contents) {
      const filled = await page.request.put(`${base}/${requestId}/boxes/${box.id}/lines/${product.id}`, {
        headers: { ...h, 'Content-Type': 'application/json' },
        data: { quantity: product.qty },
      });
      expect(filled.ok()).toBeTruthy();
    }
    const closed = await page.request.post(`${base}/${requestId}/boxes/${box.id}/close`, { headers: h });
    expect(closed.ok()).toBeTruthy();
    return box;
  };

  const scannedBox = await createFilledBox(products.slice(0, 2));
  const manualBox = await createFilledBox(products.slice(2));
  const completed = await page.request.post(`${base}/${requestId}/complete-receiving`, { headers: h });
  expect(completed.ok()).toBeTruthy();

  await page.goto('/app/ff/sorting');
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-box-putaway-row')).toHaveCount(2);

  const scanInput = page.getByTestId('ff-sorting-scan-input');
  // Ранее выбранная ячейка не должна молча примениться к следующему коробу.
  await scanInput.fill(scanLocation.barcode);
  await scanInput.press('Enter');
  await expect(page.getByTestId('ff-sorting-scan-message')).toContainText('Активная ячейка');

  let scannedBoxPutawayPosts = 0;
  await page.route(`**/boxes/${scannedBox.id}/putaway`, async (route) => {
    scannedBoxPutawayPosts += 1;
    await route.continue();
  });
  await scanInput.fill(scannedBox.internal_barcode);
  await scanInput.press('Enter');
  await expect(page.getByTestId('ff-sorting-scan-message')).toContainText(
    `Короб №${scannedBox.box_number} выбран`,
  );
  const selectedBoxRow = page
    .getByTestId('ff-sorting-box-putaway-row')
    .filter({ hasText: `Короб №${scannedBox.box_number}` });
  await expect(selectedBoxRow).toHaveAttribute('aria-selected', 'true');
  expect(scannedBoxPutawayPosts).toBe(0);
  const untouchedRows = await page.request.get(`${base}/${requestId}/distribution-lines`, { headers: h });
  expect(untouchedRows.ok()).toBeTruthy();
  expect(await untouchedRows.json()).toEqual([]);

  await scanInput.fill(scanLocation.barcode);
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/boxes/${scannedBox.id}/putaway`) &&
        response.ok(),
    ),
    scanInput.press('Enter'),
  ]);
  await expect(page.getByTestId('ff-sorting-scan-message')).toContainText(
    `Короб №${scannedBox.box_number} полностью размещён в ячейке SCAN-BOX-A-01`,
  );
  await expect(page.getByTestId('ff-sorting-box-putaway-row')).toHaveCount(1);
  expect(scannedBoxPutawayPosts).toBe(1);

  const manualRow = page
    .getByTestId('ff-sorting-box-putaway-row')
    .filter({ hasText: `Короб №${manualBox.box_number}` });
  await manualRow.getByTestId('ff-sorting-box-location').getByRole('combobox').click();
  await page.getByRole('option', { name: 'MANUAL-BOX-A-02' }).click();
  let manualBoxPutawayPosts = 0;
  await page.route(`**/boxes/${manualBox.id}/putaway`, async (route) => {
    manualBoxPutawayPosts += 1;
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.continue();
  });
  const manualSubmit = manualRow.getByTestId('ff-sorting-box-putaway-submit');
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/boxes/${manualBox.id}/putaway`) &&
        response.ok(),
    ),
    manualSubmit.click(),
    manualSubmit.click({ force: true }),
  ]);
  await expect(page.getByTestId('ff-sorting-posted-done')).toBeVisible();
  expect(manualBoxPutawayPosts).toBe(1);

  const distribution = await page.request.get(`${base}/${requestId}/distribution-lines`, { headers: h });
  expect(distribution.ok()).toBeTruthy();
  const rows = (await distribution.json()) as {
    product_id: string;
    storage_location_id: string;
    quantity: number;
  }[];
  expect(rows).toHaveLength(3);
  expect(rows.map((row) => ({
    product_id: row.product_id,
    storage_location_id: row.storage_location_id,
    quantity: row.quantity,
  })).sort((a, b) => a.product_id.localeCompare(b.product_id))).toEqual([
    { product_id: products[0]!.id, storage_location_id: scanLocation.id, quantity: products[0]!.qty },
    { product_id: products[1]!.id, storage_location_id: scanLocation.id, quantity: products[1]!.qty },
    { product_id: products[2]!.id, storage_location_id: manualLocation.id, quantity: products[2]!.qty },
  ].sort((a, b) => a.product_id.localeCompare(b.product_id)));
});

// TC-NEW-SORT-04 — sorting draft close/cross asks before losing unsaved manual corrections.
test('ff sorting: unsaved manual correction asks before close', async ({ page }) => {
  const email = `e2e-sort-dirty-${Date.now()}@example.com`;
  const sku = `SKU-SORT-DIRTY-${Date.now()}`;
  const whCode = `wh-sort-dirty-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort Dirty');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;
  await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'DIRTY-A-01' },
  });
  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар для черновика', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  const line = await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 1 },
  });
  const lineId = ((await line.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, rid);
  await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 1 },
  });
  await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });

  await page.goto('/app/ff/sorting');
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();
  const row = page.getByTestId('ff-sorting-cell-row').first();
  await selectSortingLocation(page, row, /DIRTY-A-01/);
  await expect(page.getByTestId('ff-sorting-save')).toHaveCount(0);
  await expect(page.getByTestId('ff-sorting-apply')).toBeEnabled();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Закрыть без сохранения?');
    await dialog.dismiss();
  });
  await page.getByTestId('ff-doc-dialog-close').click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Закрыть без сохранения?');
    await dialog.accept();
  });
  await page.getByTestId('ff-doc-dialog-close').click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeHidden();
});

// TC-NEW-SORT-05 — warehouse/cell CRUD keeps stock safe when a location with balance is deleted.
test('ff cells: rename and safe-delete location with balance', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const email = `e2e-cells-crud-${Date.now()}@example.com`;
  const sku = `SKU-CELL-CRUD-${Date.now()}`;
  const whCode = `wh-cell-crud-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Cells CRUD');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад CRUD', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;
  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'CRUD-A-01' },
  });
  const locId = ((await loc.json()) as { id: string }).id;
  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар в удаляемой ячейке', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  const line = await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 2 },
  });
  const lineId = ((await line.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/submit`, { headers: h });
  await beginInboundReceiving(page.request, h, rid);
  await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 2 },
  });
  await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });
  await page.request.put(`${base}/${rid}/distribution-lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: [{ product_id: pid, storage_location_id: locId, quantity: 2 }],
  });
  await page.request.post(`${base}/${rid}/distribution-complete`, { headers: h });

  await page.goto('/app/catalog');
  await expect(page.getByTestId('warehouses-panel')).toBeVisible();
  await page.getByTestId('warehouse-row').filter({ hasText: 'Склад CRUD' }).click();
  await expect(page.getByTestId('location-table')).toContainText('CRUD-A-01');
  await expect(page.getByTestId('location-table')).not.toContainText('__SORTING__');

  const warehouseRow = page.getByTestId('warehouse-row').filter({ hasText: 'Склад CRUD' });
  await warehouseRow.getByTestId('warehouse-rename').click();
  await page.getByTestId('warehouse-rename-name').getByRole('textbox').fill('Склад CRUD renamed');
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/warehouses/') && r.ok()),
    page.getByTestId('warehouse-rename-submit').click(),
  ]);
  await expect(page.getByTestId('warehouse-table')).toContainText('Склад CRUD renamed');

  const locationRow = page.getByTestId('location-row').filter({ hasText: 'CRUD-A-01' });
  await locationRow.getByTestId('location-rename').click();
  await page.getByTestId('location-rename-code').getByRole('textbox').fill('CRUD-A-02');
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/locations/') && r.ok()),
    page.getByTestId('location-rename-submit').click(),
  ]);
  await expect(page.getByTestId('location-table')).toContainText('CRUD-A-02');

  await page.getByTestId('location-row').filter({ hasText: 'CRUD-A-02' }).getByTestId('location-delete').click();
  await expect(page.getByTestId('location-delete-stock-warning')).toContainText('2 шт');
  await expect(page.getByTestId('location-delete-balances')).toContainText(sku);
  await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes('move_stock_to=unallocated') && r.status() === 204),
    page.getByTestId('location-delete-move-unallocated').click(),
  ]);
  await expect(page.getByTestId('location-table')).not.toContainText('CRUD-A-02');

  const balances = await page.request.get('/api/operations/inventory-balances/summary', { headers: h });
  const row = ((await balances.json()) as { product_id: string; quantity_in_sorting: number; quantity_in_storage: number }[])
    .find((item) => item.product_id === pid);
  expect(row).toMatchObject({ quantity_in_sorting: 2, quantity_in_storage: 0 });
});
