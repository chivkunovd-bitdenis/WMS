import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import { INBOUND_API, loginFfAdmin, seedFfSellerInbound } from './inbound-boxes-helpers';

// TC-NEW-PRINT-01 — в модалке приёмки строка товара как в эталоне: фото/артикул/ШК и кнопка печати.
test('ff inbound modal shows product catalog columns and barcode print control', async ({ page }) => {
  const seed = await seedFfSellerInbound(page);
  const h = { Authorization: `Bearer ${seed.token}` };

  const cr = await page.request.post(INBOUND_API, {
    headers: h,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(cr.ok()).toBeTruthy();
  const rid = String(((await cr.json()) as { id: string }).id);
  await page.request.post(`${INBOUND_API}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: seed.productId, expected_qty: 2 },
  });
  await page.request.post(`${INBOUND_API}/${rid}/submit`, { headers: h });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();

  const table = page.getByTestId('ff-inbound-lines-table');
  await expect(table.getByRole('columnheader', { name: 'Фото' })).toBeVisible();
  await expect(table.getByRole('columnheader', { name: 'ШК' })).toBeVisible();
  await expect(table.getByRole('button', { name: 'Печать ШК товара' }).first()).toBeVisible();
});
