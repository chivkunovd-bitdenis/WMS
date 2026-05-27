import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { fillFfInboundBoxLineQty } from './inbound-boxes-helpers';

// TC-S06-007 — остаток после verify (зона сортировки); разкладка → доступно в ячейках.
test('ff verify posts to sorting zone; sorting queue and product columns', async ({ page }) => {
  const email = `e2e-sort-${Date.now()}@example.com`;
  const sku = `SKU-SORT-${Date.now()}`;
  const whCode = `wh-sort-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort');
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
    data: { code: 'STORE-1' },
  });
  const lid = ((await loc.json()) as { id: string }).id;

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
  const prim = await page.request.post(`${base}/${rid}/primary-accept`, {
    headers: h,
    data: { actual_box_count: 1 },
  });
  const inb = ((await prim.json()) as { boxes: { internal_barcode: string }[] }).boxes[0]!
    .internal_barcode;

  await page.goto('/app/ff/reception');
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();

  await page.getByTestId('ff-inbound-box-open-scan').fill(inb);
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/boxes/open')),
    page.getByTestId('ff-inbound-box-open-submit').click(),
  ]);
  await fillFfInboundBoxLineQty(page, 4);
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/close')),
    page.getByTestId('ff-inbound-box-close').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/verify')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);

  await expect(page.getByTestId('ff-inbound-moved-to-sorting')).toBeVisible();
  await page.getByTestId('ff-doc-dialog-close').click();

  const balAfterVerify = await page.request.get('/api/operations/inventory-balances/summary', {
    headers: h,
  });
  expect(balAfterVerify.ok()).toBeTruthy();
  const row = ((await balAfterVerify.json()) as { product_id: string; quantity_in_sorting: number }[]).find(
    (r) => r.product_id === pid,
  );
  expect(row?.quantity_in_sorting).toBe(4);

  await page.goto('/app/ff/sorting');
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(page.getByTestId('ff-inbound-queue-sorting-qty').first()).toHaveText('4');

  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  const boxCard = page.getByTestId('ff-sorting-box-card').first();
  await boxCard.getByTestId('ff-sorting-box-location').click();
  await page.getByRole('option', { name: /STORE-1/ }).click();
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/putaway')),
    boxCard.getByTestId('ff-sorting-box-putaway-whole').click(),
  ]);

  const balDone = await page.request.get('/api/operations/inventory-balances/summary', { headers: h });
  const doneRow = ((await balDone.json()) as {
    product_id: string;
    quantity_in_sorting: number;
    quantity_in_storage: number;
    available: number;
  }[]).find((r) => r.product_id === pid);
  expect(doneRow?.quantity_in_sorting).toBe(0);
  expect(doneRow?.quantity_in_storage).toBe(4);
  expect(doneRow?.available).toBe(4);

  await page.goto('/app/ff/products');
  const prodRow = page.getByTestId('ff-product-row').filter({ hasText: sku });
  await expect(prodRow.getByTestId('ff-product-qty-sorting')).toHaveText('0');
  await expect(prodRow).toContainText('4');
});
