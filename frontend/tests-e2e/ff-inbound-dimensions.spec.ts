import { test, expect } from '@playwright/test';

import { waitForPatchOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

test.describe.configure({ timeout: 120_000 });

// TC-NEW-F02-DIMENSIONS — ordinary inbound: FF edits product dimensions from the receiving line.
test('FF inbound receiving shows saved product dimensions and volume', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `f02-dim-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 1, expectedQty: 1 });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await openFfInboundDoc(page, seed, { skipLogin: true });

  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Приёмка');
  await expect(page.getByTestId('ff-inbound-return-autoprint')).toHaveCount(0);

  const productRow = page
    .getByTestId('ff-inbound-lines-table')
    .locator('tbody tr')
    .filter({ hasText: seed.sku });
  await expect(productRow).toBeVisible();

  await productRow.getByTestId('ff-inbound-line-dimensions-edit').click();
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toBeVisible();
  await page.getByTestId('ff-inbound-dimensions-length').fill('200');
  await page.getByTestId('ff-inbound-dimensions-width').fill('100');
  await page.getByTestId('ff-inbound-dimensions-height').fill('50');
  await Promise.all([
    waitForPatchOk(page, '/api/products', (u) => u.includes('/dimensions')),
    page.getByTestId('ff-inbound-dimensions-save').click(),
  ]);

  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toHaveCount(0);
  await expect(productRow.getByTestId('ff-inbound-line-dimensions')).toContainText('200×100×50 мм');
  await expect(productRow.getByTestId('ff-inbound-line-dimensions')).toContainText('1.00 л');
});
