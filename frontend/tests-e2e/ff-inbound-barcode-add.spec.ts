import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import { INBOUND_API, loginFfAdmin, seedFfSellerInbound } from './inbound-boxes-helpers';

// TC-NEW-C06 — добавление строки из каталога в черновике FF.
test('ff inbound draft adds line from seller catalog picker', async ({ page }) => {
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
  const locationLoad = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return (
      request.method() === 'GET' &&
      `${url.pathname}${url.search}` ===
        `/api/warehouses/${seed.warehouseId}/locations?exclude_sorting_zone=true`
    );
  });
  const [locationLoadRequest] = await Promise.all([
    locationLoad,
    page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click(),
  ]);
  expect(`${new URL(locationLoadRequest.url()).pathname}${new URL(locationLoadRequest.url()).search}`).toBe(
    `/api/warehouses/${seed.warehouseId}/locations?exclude_sorting_zone=true`,
  );
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await page.getByTestId('ff-inbound-add-products').click();
  await expect(page.getByTestId('ff-inbound-picker')).toBeVisible();
  await page.getByTestId('ff-inbound-picker-search').fill(seed.sku);
  await page.getByTestId('ff-inbound-picker-qty').first().fill('1');
  const [lineRes] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines') && !u.includes('/lines/')),
    page.getByTestId('ff-inbound-picker-apply').click(),
  ]);
  expect(lineRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-inbound-lines-table')).toContainText(seed.sku);
});

// TC-NEW-IN-06 — отсутствующий в каталоге товар не создаётся из карточки приёмки.
test('ff inbound draft does not expose manual product creation from intake card', async ({
  page,
}) => {
  const suffix = Date.now();
  const seed = await seedFfSellerInbound(page, `manual-${suffix}`);
  const h = { Authorization: `Bearer ${seed.token}` };
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

  await expect(page.getByTestId('ff-inbound-create-manual-product')).toHaveCount(0);
  await page.getByTestId('ff-inbound-add-products').click();
  await page.getByTestId('ff-inbound-picker-search').fill(manualBarcode);
  await page.getByTestId('ff-inbound-picker-search').press('Enter');
  await expect(page.getByTestId('ff-inbound-picker-scan-error')).toContainText(
    'Товар не найден в каталоге селлера',
  );
});
