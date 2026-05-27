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
