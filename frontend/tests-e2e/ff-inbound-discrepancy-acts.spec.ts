import { expect, test } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

test('REC-07 — FF approves linked discrepancy act from inbound document', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rec07-${Date.now()}`);
  const auth = { Authorization: `Bearer ${seed.token}` };
  const inboundId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 5,
  });
  const inboundDetail = await page.request.get(`${INBOUND_API}/${inboundId}`, { headers: auth });
  expect(inboundDetail.ok()).toBeTruthy();
  const inboundLineId = String(
    ((await inboundDetail.json()) as { lines: { id: string }[] }).lines[0]!.id,
  );

  const actCreate = await page.request.post('/api/operations/discrepancy-acts', {
    headers: auth,
    data: { inbound_intake_request_id: inboundId },
  });
  expect(actCreate.ok()).toBeTruthy();
  const actId = String(((await actCreate.json()) as { id: string }).id);
  const actLine = await page.request.post(`/api/operations/discrepancy-acts/${actId}/lines`, {
    headers: auth,
    data: {
      product_id: seed.productId,
      quantity: 2,
      inbound_intake_line_id: inboundLineId,
    },
  });
  expect(actLine.ok()).toBeTruthy();
  const actSubmit = await page.request.post(`/api/operations/discrepancy-acts/${actId}/submit`, {
    headers: auth,
  });
  expect(actSubmit.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await expect(page.getByTestId('ff-inbound-discrepancy-acts')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-discrepancy-act-status')).toHaveText('Передан на FF');
  await expect(page.getByTestId('ff-inbound-discrepancy-act-line')).toContainText(seed.sku);
  await expect(page.getByTestId('ff-inbound-discrepancy-act-line')).toContainText('+2');
  await expect(page.getByTestId('ff-inbound-discrepancy-act-reject')).toBeVisible();

  await Promise.all([
    waitForPostOk(page, '/api/operations/discrepancy-acts', (u) => u.includes('/approve')),
    page.getByTestId('ff-inbound-discrepancy-act-approve').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-discrepancy-act-status')).toHaveText('Утверждено');
  await expect(page.getByTestId('ff-inbound-discrepancy-act-approve')).toHaveCount(0);

  const balances = await page.request.get('/api/operations/inventory-balances/summary', {
    headers: auth,
    params: { warehouse_id: seed.warehouseId },
  });
  expect(balances.ok()).toBeTruthy();
  const rows = (await balances.json()) as { product_id: string; quantity: number }[];
  expect(rows.find((row) => row.product_id === seed.productId)?.quantity).toBe(2);

  const movements = await page.request.get('/api/operations/inventory-movements', {
    headers: auth,
  });
  expect(movements.ok()).toBeTruthy();
  const movementRows = (await movements.json()) as {
    product_id: string;
    quantity_delta: number;
    movement_type: string;
  }[];
  expect(
    movementRows.some(
      (row) =>
        row.product_id === seed.productId &&
        row.movement_type === 'discrepancy_act' &&
        row.quantity_delta === 2,
    ),
  ).toBeTruthy();
});
