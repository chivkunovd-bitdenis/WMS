import { test, expect } from '@playwright/test';

import { INBOUND_API, loginFfAdmin, openFfInboundDoc, seedFfSellerInbound } from './inbound-boxes-helpers';

// TC-NEW-G13-003 — накладная на поставку (приёмка селлер → ФФ).
test('FF prints inbound supply waybill from intake document', async ({ page }) => {
  const seed = await seedFfSellerInbound(page);
  const h = { Authorization: `Bearer ${seed.token}`, 'Content-Type': 'application/json' };

  const cr = await page.request.post(INBOUND_API, {
    headers: h,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(cr.ok()).toBeTruthy();
  const rid = String(((await cr.json()) as { id: string }).id);

  const line = await page.request.post(`${INBOUND_API}/${rid}/lines`, {
    headers: h,
    data: { product_id: seed.productId, expected_qty: 5 },
  });
  expect(line.ok()).toBeTruthy();

  const sub = await page.request.post(`${INBOUND_API}/${rid}/submit`, { headers: h });
  expect(sub.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await openFfInboundDoc(page, seed, { skipLogin: true });

  await expect(page.getByTestId('ff-inbound-lines-table')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-print-waybill')).toBeVisible();
  await page.getByTestId('ff-inbound-print-waybill').click();
});
