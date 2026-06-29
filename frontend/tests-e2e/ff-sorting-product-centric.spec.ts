import { test, expect, type Locator } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

async function sortingRowByQty(card: Locator, qty: string): Promise<Locator> {
  const rows = card.getByTestId('ff-sorting-cell-row');
  const count = await rows.count();
  for (let i = 0; i < count; i++) {
    const row = rows.nth(i);
    const value = await row.getByTestId('ff-sorting-cell-qty').inputValue();
    if (value === qty) return row;
  }
  throw new Error(`sorting row with qty ${qty} not found`);
}

// TC-NEW-SORT-01 — mixed loose + box distribution survives save/reload with correct sources.
test('ff sorting product-centric: loose and box sources persist after save reload', async ({ page }) => {
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

  const doc = await page.request.get(`${base}/${rid}`, { headers: h });
  expect(doc.ok()).toBeTruthy();
  const lineId = ((await doc.json()) as { lines: { id: string }[] }).lines[0]!.id;

  const boxRes = await page.request.post(`${base}/${rid}/boxes`, { headers: h });
  expect(boxRes.ok()).toBeTruthy();
  const boxId = ((await boxRes.json()) as { id: string }).id;
  const putBox = await page.request.put(`${base}/${rid}/boxes/${boxId}/lines/${pid}`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { quantity: 6 },
  });
  expect(putBox.ok()).toBeTruthy();
  const closeBox = await page.request.post(`${base}/${rid}/boxes/${boxId}/close`, { headers: h });
  expect(closeBox.ok()).toBeTruthy();

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
  await expect(page.getByTestId('ff-sorting-product-accepted')).toHaveText('10');

  const productCard = page.getByTestId('ff-sorting-product-card').first();

  await productCard.getByTestId('ff-sorting-add-cell').click();
  await expect(productCard.getByTestId('ff-sorting-cell-row')).toHaveCount(1);
  let looseRow = productCard.getByTestId('ff-sorting-cell-row').first();
  await looseRow.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: /LOOSE-1/ }).click();
  await looseRow.getByTestId('ff-sorting-cell-qty').fill('4');

  await productCard.getByTestId('ff-sorting-add-cell').click();
  const boxRow = productCard.getByTestId('ff-sorting-cell-row').nth(1);
  await boxRow.getByTestId('ff-sorting-cell-source').click();
  await page.getByRole('option', { name: /Короб/ }).click();
  await boxRow.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: /BOX-1/ }).click();
  await boxRow.getByTestId('ff-sorting-cell-qty').fill('6');

  await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'PUT' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.getByTestId('ff-sorting-save').click(),
  ]);

  await page.reload();
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  const [reloadDistributionRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.getByTestId('ff-inbound-queue-row').first().click(),
  ]);
  expect(reloadDistributionRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();
  const reloadedCard = page.getByTestId('ff-sorting-product-card').first();
  await expect(reloadedCard.getByTestId('ff-sorting-cell-row')).toHaveCount(2);

  looseRow = await sortingRowByQty(reloadedCard, '4');
  const reloadedBoxRow = await sortingRowByQty(reloadedCard, '6');
  await expect(looseRow.getByTestId('ff-sorting-cell-source')).toContainText('Россыпь');
  await expect(reloadedBoxRow.getByTestId('ff-sorting-cell-source')).toContainText('Короб');
});

// TC-REV-SORT-FE-01 — «Упаковать» из сортировки открывает /app/ff/packaging с заданием.
test('ff sorting: pack button navigates to app packaging with task', async ({ page }) => {
  const email = `e2e-sort-pack-${Date.now()}@example.com`;
  const sku = `SKU-SORT-PACK-${Date.now()}`;
  const whCode = `wh-sort-pack-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort Pack');
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
    data: { product_id: pid, expected_qty: 4 },
  });
  await page.request.post(`${base}/${rid}/submit`, { headers: h });

  const doc = await page.request.get(`${base}/${rid}`, { headers: h });
  expect(doc.ok()).toBeTruthy();
  const lineId = ((await doc.json()) as { lines: { id: string }[] }).lines[0]!.id;

  const patchActual = await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 4 },
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
  await expect(page.getByTestId('ff-sorting-pack-btn')).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/packaging-tasks') &&
        r.ok(),
    ),
    page.getByTestId('ff-sorting-pack-btn').click(),
  ]);

  await expect(page).toHaveURL(/\/app\/ff\/packaging$/);
  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible();
});

// TC-REV-SORT-FE-02 — failed GET distribution-lines keeps last-known-good and blocks save/apply.
test('ff sorting: failed distribution-lines load shows error and blocks save', async ({ page }) => {
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
  await productCard.getByTestId('ff-sorting-add-cell').click();
  const row = productCard.getByTestId('ff-sorting-cell-row').first();
  await row.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: /CELL-A/ }).click();
  await row.getByTestId('ff-sorting-cell-qty').fill('5');

  await Promise.all([
    page.waitForResponse(
      (r) => r.request().method() === 'PUT' && r.url().includes('/distribution-lines') && r.ok(),
    ),
    page.getByTestId('ff-sorting-save').click(),
  ]);
  await expect(productCard.getByTestId('ff-sorting-cell-row')).toHaveCount(1);
  await expect(row.getByTestId('ff-sorting-cell-qty')).toHaveValue('5');

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
  await expect(page.getByTestId('ff-sorting-save')).toBeDisabled();
  await expect(page.getByTestId('ff-sorting-apply')).toBeDisabled();

  const putPromise = page.waitForRequest(
    (req) => req.method() === 'PUT' && req.url().includes('/distribution-lines'),
    { timeout: 1500 },
  );
  await page.getByTestId('ff-sorting-save').click({ force: true }).catch(() => undefined);
  await expect(putPromise).rejects.toThrow();
});
