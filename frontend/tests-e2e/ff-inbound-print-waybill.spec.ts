import { test, expect } from '@playwright/test';

import { waitForPatchOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

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

// TC-NEW-IN-08 — накладная приёмки после проведения печатает факт и расхождение без raw ID/status/FBS-мусора.
test('FF prints conducted inbound waybill with fact and discrepancy only', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `print-fact-${Date.now()}`);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 5,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await openFfInboundDoc(page, seed, { skipLogin: true });

  await expect(page.getByTestId('ff-inbound-lines-table')).toBeVisible();
  const documentNumber = (await page.getByTestId('ff-inbound-document-number').textContent())?.trim() ?? '';
  await expect(page.getByTestId('ff-inbound-compact-summary')).toContainText('Box Seller');
  await expect(page.getByTestId('ff-inbound-boxes-summary')).toContainText('0 из 1');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('3');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('3');

  await page.getByTestId('ff-inbound-verify-complete').click();
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-discrepancy-line')).toContainText('Недостача 2');
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');

  await page.evaluate(() => {
    (
      window as unknown as {
        __WMS_CAPTURE_PRINT_HTML__?: boolean;
        __WMS_LAST_PRINT_HTML__?: string;
      }
    ).__WMS_CAPTURE_PRINT_HTML__ = true;
    (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ = '';
  });
  await page.getByTestId('ff-inbound-print-waybill').click();

  await expect
    .poll(async () =>
      page.evaluate(
        () => (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ ?? '',
      ),
    )
    .toContain('Недостача 2');

  const html = await page.evaluate(
    () => (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ ?? '',
  );
  expect(html).toContain('SKU/товар');
  expect(html).toContain('Заявлено');
  expect(html).toContain('Факт');
  expect(html).toContain('Расхождение');
  expect(html).toContain(seed.sku);
  expect(html).toContain('Box Product');
  expect(html).toContain('<td align="right">5</td>');
  expect(html).toContain('<td align="right">3</td>');
  expect(html).toContain('Недостача 2');
  expect(html).toContain('Поставка');
  expect(html).toContain(documentNumber);
  expect(html).toContain('Box Seller');
  expect(html).toContain('WH (');
  expect(html).toContain('Короба (план / факт)');
  expect(html).toContain('1 / 0');
  expect(html).not.toContain(requestId);
  expect(html).not.toContain(seed.warehouseId);
  expect(html).not.toContain('Факт — в системе WMS');
  expect(html).not.toContain('status');
  expect(html).not.toContain('sorting');
  expect(html).not.toContain('В сортировке');
  expect(html).not.toContain('QR заказа WB');
  expect(html).not.toContain('WB-заказ');
  expect(html).not.toContain('FBS');
  expect(html).not.toContain('order sticker');
});
