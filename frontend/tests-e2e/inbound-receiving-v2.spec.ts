import { test, expect } from '@playwright/test';

import { waitForPatchOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  loginSellerPortal,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-IN-01 — очередь с человеческой идентичностью, скан в приёмку, ручная правка, завершение с модалкой расхождений.
test('inbound receiving v2 — scan, manual edit, finish with discrepancy', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 3,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-inbound-queue-document').first()).toContainText('№');
  await expect(page.getByTestId('ff-inbound-queue-row').first()).toContainText('Box Seller');
  await expect(page.getByTestId('ff-inbound-queue-composition').first()).toContainText('1 поз.');
  await expect(page.getByTestId('ff-inbound-queue-composition').first()).toContainText('ед.');
  await expect(page.getByTestId('ff-inbound-queue-boxes').first()).toContainText('0 из 1');
  await expect(page.getByTestId('ff-inbound-queue-status').first()).toContainText('Передано');
  await page.getByTestId('ff-inbound-queue-row').first().focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root').getByRole('tab', { name: /упаковка/i })).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-compact-summary')).toContainText('Box Seller');
  await expect(page.getByTestId('ff-inbound-received-summary')).toContainText('0 из 3');
  await expect(page.getByTestId('ff-inbound-boxes-summary')).toContainText('0 из 1');
  await expect(page.getByTestId('ff-inbound-discrepancy-summary')).toContainText('Расхождения');
  const tableLayout = await page.getByTestId('ff-inbound-lines-table').evaluate((table) => {
    const container = table.closest('.MuiTableContainer-root');
    const headCells = Array.from(table.querySelectorAll('thead th'));
    const firstBodyCells = Array.from(table.querySelectorAll('tbody tr:first-child td'));
    const acceptedHead = headCells.find((cell) => cell.textContent?.trim() === 'Принято');
    const acceptedBody = firstBodyCells[firstBodyCells.length - 1];
    return {
      table: table.getBoundingClientRect().width,
      container: container?.getBoundingClientRect().width ?? 0,
      headerCells: headCells.length,
      bodyCells: firstBodyCells.length,
      acceptedHeadRight: acceptedHead?.getBoundingClientRect().right ?? 0,
      acceptedBodyRight: acceptedBody?.getBoundingClientRect().right ?? 0,
    };
  });
  expect(tableLayout.table).toBeGreaterThanOrEqual(tableLayout.container - 1);
  expect(tableLayout.headerCells).toBe(tableLayout.bodyCells);
  expect(Math.abs(tableLayout.acceptedHeadRight - tableLayout.acceptedBodyRight)).toBeLessThanOrEqual(1);

  const linesTable = page.getByTestId('ff-inbound-lines-table');
  await expect(linesTable.getByRole('button', { name: 'Печать ШК товара' }).first()).toBeVisible();

  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('0');

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-input').press('Enter'),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('1');
  await expect(page.getByTestId('ff-inbound-receiving-scan-input')).toBeFocused();
  await expect(page.getByTestId('ff-inbound-received-summary')).toContainText('1 из 3');

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  const manualActual = page.getByTestId('ff-inbound-line-actual');
  await manualActual.fill('2.9');
  await manualActual.press('Enter');
  await expect(manualActual).toBeFocused();
  await expect(page.getByText('Только целое количество без дробей.')).toBeVisible();
  await manualActual.fill('');
  await manualActual.press('Enter');
  await expect(manualActual).toBeFocused();
  await expect(page.getByText('Укажите целое количество.')).toBeVisible();
  await manualActual.fill('2');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('2');
  await expect(page.getByTestId('ff-inbound-line-row-discrepancy')).toBeVisible();

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  const actualField = page.getByTestId('ff-inbound-line-actual').first();
  await actualField.click();
  await actualField.fill('');
  await actualField.pressSequentially('100');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    actualField.blur(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('100');

  await page.getByTestId('ff-inbound-verify-complete').click();
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-discrepancy-line')).toContainText(seed.sku);
  await expect(page.getByTestId('ff-inbound-discrepancy-line')).toContainText('Излишек 97');
  await expect(page.getByTestId('ff-inbound-discrepancy-box-summary')).toContainText('Короба: 0 из 1');
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
    await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(i + 1);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  }
  await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(3);
  await expect(page.getByTestId('ff-inbound-box-row').nth(0)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-row').nth(1)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-row').nth(2)).toContainText('Пока нет товаров');

  await page.getByTestId('ff-inbound-box-row').nth(1).getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-box-label')).toContainText('Короб № 2');
  await expect(page.getByTestId(`ff-inbound-box-add-line-row-${seed.productId}`)).toBeVisible();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toContainText('Короб № 2');
  await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
    page.getByTestId('ff-inbound-box-add-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-box-add-manual-qty').first()).toHaveValue('1');
  await page.getByTestId('ff-inbound-box-add-dismiss').click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-box-row').nth(1)).toContainText(seed.sku);
  await expect(page.getByTestId('ff-inbound-add-to-box')).toBeEnabled();

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(seed.sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('2', {
    timeout: 20_000,
  });
  await expect(page.getByTestId('ff-inbound-box-row').nth(1)).toContainText('1');
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

// TC-NEW-IN-05 — возврат: скан товара селлера вне заявки создаёт красное расхождение, габариты сохраняются из строки.
test('inbound receiving v2 — return accepts seller catalog discrepancy and dimensions', async ({
  page,
}) => {
  const suffix = `rcv-return-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const factSku = `sku-return-fact-${suffix}`;
  const factBarcode = `wb-return-fact-${suffix}`;
  const otherSellerName = `Other Return Seller ${suffix}`;

  const otherSeller = await page.request.post('/api/sellers', {
    headers: adminHeaders,
    data: { name: otherSellerName },
  });
  expect(otherSeller.ok()).toBeTruthy();

  const factProductRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'Return Fact Product',
      sku_code: factSku,
      wb_barcode: factBarcode,
      seller_id: seed.sellerId,
      length_mm: 120,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(factProductRes.ok()).toBeTruthy();

  const sellerLogin = await page.request.post('/api/auth/login', {
    data: { email: seed.sellerEmail, password: seed.password },
  });
  expect(sellerLogin.ok()).toBeTruthy();
  const sellerToken = String(((await sellerLogin.json()) as { access_token: string }).access_token);
  const sellerHeaders = { Authorization: `Bearer ${sellerToken}` };

  const createReturn = await page.request.post(INBOUND_API, {
    headers: sellerHeaders,
    data: { warehouse_id: seed.warehouseId, operation_type: 'return' },
  });
  expect(createReturn.ok()).toBeTruthy();
  const requestId = String(((await createReturn.json()) as { id: string }).id);
  const addPlannedLine = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers: sellerHeaders,
    data: { product_id: seed.productId, expected_qty: 1 },
  });
  expect(addPlannedLine.ok()).toBeTruthy();
  const submitReturn = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitReturn.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Возврат');
  await expect(page.getByTestId('ff-inbound-return-autoprint')).toBeVisible();
  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-seller').click();
  const sellerListbox = page.getByRole('listbox');
  await expect(sellerListbox.getByText(/Box Seller/)).toBeVisible();
  await expect(sellerListbox.getByText(otherSellerName, { exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Отмена' }).click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  await page.getByTestId('ff-inbound-return-autoprint').click();
  await page.evaluate(() => {
    (
      window as unknown as {
        __WMS_CAPTURE_PRINT_HTML__?: boolean
        __WMS_LAST_PRINT_HTML__?: string
      }
    ).__WMS_CAPTURE_PRINT_HTML__ = true;
    (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ = '';
  });

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(factBarcode);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  await page.waitForFunction(
    (barcode) =>
      Boolean(
        (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__?.includes(
          String(barcode),
        ),
      ),
    factBarcode,
  );

  const factRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: factSku });
  await expect(factRow).toBeVisible();
  await expect(factRow).toContainText('Добавлено ФФ');
  await expect(factRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');

  await factRow.getByTestId('ff-inbound-line-dimensions-edit').click();
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toBeVisible();
  await page.getByTestId('ff-inbound-dimensions-length').fill('200');
  await page.getByTestId('ff-inbound-dimensions-width').fill('100');
  await page.getByTestId('ff-inbound-dimensions-height').fill('50');
  await Promise.all([
    waitForPatchOk(page, '/api/products', (u) => u.includes('/dimensions')),
    page.getByTestId('ff-inbound-dimensions-save').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toHaveCount(0);
  await expect(factRow.getByTestId('ff-inbound-line-dimensions')).toContainText('200×100×50 мм');
  await expect(factRow.getByTestId('ff-inbound-line-dimensions')).toContainText('1.00 л');

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  await page.getByTestId('seller-documents-row').filter({ hasText: 'Поставка' }).first().click();
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible();
  const sellerFactRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: factSku });
  await expect(sellerFactRow).toBeVisible();
  await expect(sellerFactRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText(
    'Добавлено ФФ',
  );
  await expect(sellerFactRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  await expect(sellerFactRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  await expect(sellerFactRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('+1');
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
  await page.getByTestId('ff-inbound-box-row').first().getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();

  for (let i = 0; i < 6; i++) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ]);
  }
  await page.getByTestId('ff-inbound-box-add-dismiss').click();
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
