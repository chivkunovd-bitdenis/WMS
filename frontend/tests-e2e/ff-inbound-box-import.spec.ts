import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import { BOX_IMPORT_BAD_XLSX, tempCombainXlsx } from './box-import-helpers';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-BOX-001 — xlsx «Штрих-код комбайн» → preview → apply → короба на приёмке.
test.describe('FF inbound box import from xlsx', () => {
  test('TC-NEW-BOX-001 happy path creates boxes from combain xlsx', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const xlsxPath = tempCombainXlsx([
      { barcode: seed.sku, qty: 2, address: '1' },
      { barcode: seed.sku, qty: 1, address: '2' },
    ]);

    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 2,
      expectedQty: 10,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    await beginInboundReceiving(page.request, h, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await expect(page.getByTestId('ff-inbound-import-boxes')).toBeVisible();
    await page.getByTestId('ff-inbound-import-boxes').click();
    await expect(page.getByTestId('ff-inbound-box-import-dialog')).toBeVisible();

    const fileInput = page.getByTestId('ff-inbound-box-import-file-input').locator('input[type="file"]');
    await fileInput.setInputFiles(xlsxPath);

    await expect(page.getByTestId('ff-inbound-box-import-summary')).toContainText('2', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('ff-inbound-box-import-summary')).toContainText('3');

    const [applyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/import-boxes/apply')),
      page.getByTestId('ff-inbound-box-import-apply').click(),
    ]);
    expect(applyRes.ok()).toBeTruthy();

    await expect(page.getByTestId('ff-inbound-import-success-snackbar')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(2, { timeout: 15_000 });
  });

  test('TC-NEW-BOX-001-N1 bad xlsx shows format error and does not create boxes', async ({
    page,
  }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 5,
    });
    await beginInboundReceiving(page.request, { Authorization: `Bearer ${seed.token}` }, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await page.getByTestId('ff-inbound-import-boxes').click();
    await expect(page.getByTestId('ff-inbound-box-import-dialog')).toBeVisible();

    const fileInput = page.getByTestId('ff-inbound-box-import-file-input').locator('input[type="file"]');
    await fileInput.setInputFiles(BOX_IMPORT_BAD_XLSX);

    await expect(page.getByTestId('ff-inbound-box-import-format-error')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('ff-inbound-box-import-apply')).toBeDisabled();
    await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(0);
  });
});
