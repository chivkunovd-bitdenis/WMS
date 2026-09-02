import { expect, test } from '@playwright/test';

import { waitForPatchOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  expandInboundPackages,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-IN-08 — ручной факт является общим количеством, включая все контейнеры.
test('inbound receiving — manual total stays exact with cargo place and rejects a lower total', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-container-total-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 5,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.includes('/begin-receiving')),
    page.getByTestId('ff-inbound-submit-warehouse').click(),
  ]);
  await expandInboundPackages(page);

  await page.getByTestId('ff-inbound-create-cargo-places').click();
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.endsWith('/cargo-places')),
    page.getByTestId('ff-inbound-cargo-places-create').click(),
  ]);
  await page.getByTestId('ff-inbound-cargo-place-row').first().getByRole('button', { name: 'Наполнить' }).click();
  const cargoQty = page.getByTestId('ff-inbound-box-add-manual-qty').first();
  await cargoQty.fill('2');
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' &&
        response.url().includes('/cargo-places/') &&
        response.url().includes(`/lines/${seed.productId}`) &&
        response.status() === 200,
    ),
    cargoQty.press('Enter'),
  ]);
  await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.includes('/cargo-places/') && url.endsWith('/scan')),
    page.getByTestId('ff-inbound-box-add-scan-submit').click(),
  ]);
  await page.getByTestId('ff-inbound-box-add-dismiss').click();
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('3');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('5');
  const loosePatch = page.waitForRequest((request) => {
    if (!request.url().includes('/actual') || request.method() !== 'PATCH') return false;
    const body = JSON.parse(request.postData() ?? '{}') as { actual_qty?: number };
    return body.actual_qty === 2;
  });
  await Promise.all([
    loosePatch,
    waitForPatchOk(page, INBOUND_API, (url) => url.includes('/actual')),
    page.getByTestId('ff-inbound-line-actual').press('Enter'),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('5');

  await page.reload();
  await openFfInboundDoc(page, seed, { skipLogin: true });
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('5');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  const manualActual = page.getByTestId('ff-inbound-line-actual');
  await manualActual.fill('2');
  await page.getByTestId('ff-inbound-line-expected').first().click();
  await expect(manualActual).toBeFocused();
  await expect(page.getByText(/Нельзя указать меньше 3/)).toBeVisible();
  await expect(manualActual).toHaveValue('2');
});
