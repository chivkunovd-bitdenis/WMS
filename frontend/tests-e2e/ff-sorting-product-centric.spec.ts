import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-SORT-FE-01 — товар-центричная сортировка: 2 ячейки 100/100; UI блокирует превышение принятого.
test('ff sorting product-centric — split 100/100 and block over-accepted', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `sort-pc-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 0,
    expectedQty: 200,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('200');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('200');

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);
  await page.getByTestId('ff-doc-dialog-close').click();

  const locA = await page.request.post(`/api/warehouses/${seed.warehouseId}/locations`, {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: { code: 'CELL-A' },
  });
  expect(locA.ok()).toBeTruthy();
  const locB = await page.request.post(`/api/warehouses/${seed.warehouseId}/locations`, {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: { code: 'CELL-B' },
  });
  expect(locB.ok()).toBeTruthy();

  await page.goto('/app/ff/sorting');
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  const productCard = page.getByTestId('ff-sorting-product-card').first();
  await expect(productCard.getByTestId('ff-sorting-product-accepted')).toHaveText('200');
  await expect(productCard.getByTestId('ff-sorting-product-remaining')).toHaveText('200');

  await productCard.getByTestId('ff-sorting-add-cell').click();
  let cellRow = productCard.getByTestId('ff-sorting-cell-row').first();
  await cellRow.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: 'CELL-A' }).click();
  await cellRow.getByTestId('ff-sorting-cell-qty').fill('100');
  await expect(productCard.getByTestId('ff-sorting-product-remaining')).toHaveText('100');

  await productCard.getByTestId('ff-sorting-add-cell').click();
  cellRow = productCard.getByTestId('ff-sorting-cell-row').nth(1);
  await cellRow.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: 'CELL-B' }).click();
  await cellRow.getByTestId('ff-sorting-cell-qty').fill('100');
  await expect(productCard.getByTestId('ff-sorting-product-remaining')).toHaveText('0');
  await expect(productCard.getByTestId('ff-sorting-add-cell')).toHaveCount(0);

  await productCard.getByTestId('ff-sorting-cell-row').first().getByTestId('ff-sorting-cell-qty').fill('150');
  await expect(page.getByTestId('ff-sorting-save')).toBeDisabled();
  await expect(page.getByTestId('ff-sorting-apply')).toBeDisabled();

  await productCard.getByTestId('ff-sorting-cell-row').first().getByTestId('ff-sorting-cell-qty').fill('100');
  await expect(page.getByTestId('ff-sorting-save')).toBeEnabled();

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/distribution-complete')),
    page.getByTestId('ff-sorting-apply').click(),
  ]);
  await expect(page.getByTestId('ff-sorting-all-done')).toBeVisible();
});

// TC-NEW-SORT-FE-01 — россыпь без коробов отображается на сортировке.
test('ff sorting shows loose-only accepted product', async ({ page }) => {
  const email = `e2e-loose-sort-${Date.now()}@example.com`;
  const sku = `SKU-LOOSE-SORT-${Date.now()}`;
  const whCode = `wh-ls-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Loose Sort');
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
    data: { code: 'STORE-LOOSE' },
  });

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Россыпь', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
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
  await page.request.post(`${base}/${rid}/begin-receiving`, { headers: h });
  const detail = await page.request.get(`${base}/${rid}`, { headers: h });
  const lineId = ((await detail.json()) as { lines: { id: string }[] }).lines[0]!.id;
  await page.request.patch(`${base}/${rid}/lines/${lineId}/actual`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { actual_qty: 5 },
  });
  await page.request.post(`${base}/${rid}/complete-receiving`, { headers: h });

  await page.goto('/app/ff/sorting');
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();
  await expect(page.getByTestId('ff-sorting-no-products')).toHaveCount(0);
  await expect(page.getByTestId('ff-sorting-product-card')).toHaveCount(1);
  await expect(page.getByTestId('ff-sorting-product-accepted')).toHaveText('5');
});
