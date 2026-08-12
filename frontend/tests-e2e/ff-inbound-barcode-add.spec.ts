import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import { INBOUND_API, loginFfAdmin, seedFfSellerInbound } from './inbound-boxes-helpers';

// TC-NEW-C06 — добавление строки по штрихкоду/артикулу в черновике FF.
test('ff inbound draft adds line by barcode scan field', async ({ page }) => {
  const seed = await seedFfSellerInbound(page);
  const h = { Authorization: `Bearer ${seed.token}` };

  const cr = await page.request.post(INBOUND_API, {
    headers: h,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(cr.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await page.getByTestId('ff-inbound-line-barcode-scan').fill(seed.sku);
  const [lineRes] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines') && !u.includes('/lines/')),
    page.getByTestId('ff-inbound-line-barcode-add').click(),
  ]);
  expect(lineRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-inbound-lines-table')).toContainText(seed.sku);
});

// TC-NEW-IN-06 — аварийный ручной товар создаётся прямо из карточки приёмки и попадает в заявку.
test('ff inbound draft creates manual product from intake card', async ({ page }) => {
  const suffix = Date.now();
  const seed = await seedFfSellerInbound(page, `manual-${suffix}`);
  const h = { Authorization: `Bearer ${seed.token}` };
  const manualSku = `manual-inbound-${suffix}`;
  const manualBarcode = `manual-barcode-${suffix}`;

  const cr = await page.request.post(INBOUND_API, {
    headers: h,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(cr.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await page.getByTestId('ff-inbound-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-seller').click();
  await page.getByRole('option', { name: /Box Seller/ }).click();
  await page.getByTestId('ff-manual-product-name').fill('Manual Inbound Product');
  await page.getByTestId('ff-manual-product-sku').fill(manualSku);
  await page.getByTestId('ff-manual-product-barcode').fill(manualBarcode);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines') && !u.includes('/lines/')),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);

  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-lines-table')).toContainText(manualSku);
  await expect(page.getByTestId('ff-inbound-lines-table')).toContainText('1');
});
