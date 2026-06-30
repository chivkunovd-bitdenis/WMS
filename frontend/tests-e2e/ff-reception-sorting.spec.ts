import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

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

  await page.goto('/app/ff/reception');
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();

  await page.getByTestId('ff-inbound-add-to-box').click();
  await page.getByTestId('ff-inbound-box-row').first().getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
  for (let i = 0; i < 4; i++) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(sku);
    await Promise.all([
      waitForPostOk(page, base, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ]);
  }
  await page.getByTestId('ff-inbound-box-add-dismiss').click();
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/complete-receiving')),
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

  // TC-NEW-PRINT-02 — после закрытия приёмки печать ШК доступна в сортировке.
  const linesTable = page.getByTestId('ff-inbound-lines-table');
  await expect(linesTable).toBeVisible();
  await linesTable.getByRole('button', { name: 'Печать ШК товара' }).first().click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toBeVisible();
  await page.getByTestId('ff-product-label-cancel').click();

  const productCard = page.getByTestId('ff-sorting-product-card').first();
  await expect(productCard.getByTestId('ff-sorting-cell-row')).toHaveCount(1);
  const cellRow = productCard.getByTestId('ff-sorting-cell-row').first();
  await expect(cellRow.getByTestId('ff-sorting-cell-source')).toContainText('Короб');
  await cellRow.getByTestId('ff-sorting-cell-location').click();
  await page.getByRole('option', { name: /STORE-1/ }).click();
  await expect(cellRow.getByTestId('ff-sorting-cell-qty')).toHaveValue('4');
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/distribution-complete')),
    page.getByTestId('ff-sorting-apply').click(),
  ]);
  await expect(page.getByTestId('ff-sorting-all-done')).toBeVisible();

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

  // TC-NEW-PRINT-03 — печать ШК из каталога товаров ФФ.
  await prodRow.getByRole('button', { name: 'Печать ШК товара' }).click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toBeVisible();
  await page.getByTestId('ff-product-label-cancel').click();
});
