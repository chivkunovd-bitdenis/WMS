import { test, expect } from '@playwright/test';

import { waitForPatchOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-IN-01 — скан в приёмку, ручная правка, завершение с модалкой расхождений.
test('inbound receiving v2 — scan, manual edit, finish with discrepancy', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 3,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('0');

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-input').press('Enter'),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('1');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('2');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('2');
  await expect(page.getByTestId('ff-inbound-line-row-discrepancy')).toBeVisible();

  await page.getByTestId('ff-inbound-verify-complete').click();
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
});

// TC-NEW-IN-02 — несколько коробов: отдельные кнопки, отдельное наполнение, общий скан.
test('inbound receiving v2 — multiple boxes stay independent', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-box-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 0,
    expectedQty: 2,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  for (let i = 0; i < 3; i++) {
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.endsWith('/boxes')),
      page.getByTestId('ff-inbound-add-to-box').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-box-open')).toHaveCount(i + 1);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  }
  await expect(page.getByTestId('ff-inbound-box-open')).toHaveCount(3);
  await expect(page.getByTestId('ff-inbound-box-open').nth(0)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-open').nth(1)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-open').nth(2)).toContainText('Пока нет товаров');

  await page.getByTestId('ff-inbound-box-open').nth(1).getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-box-label')).toContainText('Короб № 2');
  await expect(page.getByTestId(`ff-inbound-box-add-line-row-${seed.productId}`)).toBeVisible();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toContainText('Короб № 2');
  await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
    page.getByTestId('ff-inbound-box-add-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-box-add-qty')).toHaveText('1');
  await page.getByTestId('ff-inbound-box-add-close').click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-box-open').nth(1)).toContainText(seed.sku);
  await expect(page.getByTestId('ff-inbound-add-to-box')).toBeEnabled();

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('1', {
    timeout: 20_000,
  });
  await expect(page.getByTestId('ff-inbound-box-open').nth(1)).toContainText('1');
  await expect(page.getByText(/закройте короб/i)).toHaveCount(0);

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
});

// TC-NEW-IN-03 — чужой штрихкод в общую приёмку → тост-ошибка.
test('inbound receiving v2 — foreign barcode shows toast error', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-foreign-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 0, expectedQty: 2 });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-input')).toBeVisible();

  await page.getByTestId('ff-inbound-receiving-scan-input').fill('UNKNOWN-BARCODE-999');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes('/receiving/scan') &&
        r.request().method() === 'POST' &&
        r.status() === 422,
    ),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-scan-error-snackbar')).toContainText(
    'Товар не найден в этой поставке',
  );
});

// TC-NEW-IN-04 — короб 6 шт. + ручная правка итога до 10 → PATCH loose=4, без double count.
test('inbound receiving v2 — manual edit with box saves loose not total', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-mix-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 0,
    expectedQty: 10,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  await page.getByTestId('ff-inbound-add-to-box').click();
  await page.getByTestId('ff-inbound-box-open').first().getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();

  for (let i = 0; i < 6; i++) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ]);
  }
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
    page.getByTestId('ff-inbound-box-add-close-box').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('6');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('10');

  const patchLoose = page.waitForRequest(
    (r) => {
      if (!r.url().includes('/actual') || r.method() !== 'PATCH') {
        return false;
      }
      const body = JSON.parse(r.postData() ?? '{}') as { actual_qty?: number };
      return body.actual_qty === 4;
    },
  );
  await Promise.all([
    patchLoose,
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);

  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('10');
  await expect(page.getByTestId('ff-inbound-line-row-match')).toBeVisible();

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
});
