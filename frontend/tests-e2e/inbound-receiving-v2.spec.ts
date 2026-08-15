import { test, expect, type Page } from '@playwright/test';

import { waitForPatchOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  loginFfAdmin,
  loginSellerPortal,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

const PRINT_SENTINEL = '__NO_PRINT__';

async function armPrintCapture(page: Page) {
  await page.evaluate((sentinel) => {
    const captureWindow = window as unknown as {
      __WMS_CAPTURE_PRINT_HTML__?: boolean;
      __WMS_LAST_PRINT_HTML__?: string;
    };
    captureWindow.__WMS_CAPTURE_PRINT_HTML__ = true;
    captureWindow.__WMS_LAST_PRINT_HTML__ = sentinel;
  }, PRINT_SENTINEL);
}

async function lastCapturedPrintHtml(page: Page): Promise<string> {
  return page.evaluate(() => {
    const captureWindow = window as unknown as { __WMS_LAST_PRINT_HTML__?: string };
    return captureWindow.__WMS_LAST_PRINT_HTML__ ?? '';
  });
}

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
  await linesTable.getByRole('button', { name: 'Печать ШК товара' }).first().click();
  const printDialog = page.getByTestId('marking-print-dialog');
  await expect(printDialog).toBeVisible();
  await expect(printDialog).not.toContainText(/упаковк/i);
  await expect(printDialog.getByTestId('marking-print-qty')).toContainText('К печати: 1');
  await expect(printDialog.getByLabel('Количество этикеток')).toBeVisible();
  await printDialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(printDialog).toHaveCount(0);

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
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
});

// TC-NEW-IN-05 — F19 negative: ordinary inbound receiving does not expose the return autoprint switch.
test('inbound receiving v2 — ordinary receiving hides return autoprint switch', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-no-return-switch-${Date.now()}`);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Поставка');
  await expect(page.getByTestId('ff-inbound-return-autoprint')).toHaveCount(0);
});

// TC-NEW-IN-01 — mobile geometry: max-length SKU/WB barcode scrolls inside the table, not the document.
test('inbound receiving v2 — mobile receiving table keeps max identifiers inside internal overflow', async ({
  page,
}) => {
  const suffix = `rcv-mobile-overflow-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const longSku = `SKU-${suffix}-`.padEnd(128, 'S');
  const longBarcode = `WB-${suffix}-`.padEnd(64, '9');

  const productRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'Mobile Overflow Product',
      sku_code: longSku,
      wb_barcode: longBarcode,
      seller_id: seed.sellerId,
      length_mm: 120,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(productRes.ok()).toBeTruthy();
  const productId = String(((await productRes.json()) as { id: string }).id);

  const sellerLogin = await page.request.post('/api/auth/login', {
    data: { email: seed.sellerEmail, password: seed.password },
  });
  expect(sellerLogin.ok()).toBeTruthy();
  const sellerToken = String(((await sellerLogin.json()) as { access_token: string }).access_token);
  const sellerHeaders = { Authorization: `Bearer ${sellerToken}` };

  const createRes = await page.request.post(INBOUND_API, {
    headers: sellerHeaders,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(createRes.ok()).toBeTruthy();
  const requestId = String(((await createRes.json()) as { id: string }).id);

  const patchRes = await page.request.patch(`${INBOUND_API}/${requestId}`, {
    headers: { ...sellerHeaders, 'Content-Type': 'application/json' },
    data: { planned_box_count: 1 },
  });
  expect(patchRes.ok()).toBeTruthy();
  const lineRes = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers: { ...sellerHeaders, 'Content-Type': 'application/json' },
    data: { product_id: productId, expected_qty: 1 },
  });
  expect(lineRes.ok()).toBeTruthy();
  const submitRes = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitRes.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });

  const linesTable = page.getByTestId('ff-inbound-lines-table');
  const longSkuCell = linesTable.getByTestId('ff-inbound-line-sku');
  const longBarcodeCell = linesTable.getByTestId('ff-inbound-line-barcode');
  const dimensionsButton = linesTable.getByTestId('ff-inbound-line-dimensions-edit');
  await expect(longSkuCell).toContainText(longSku);
  await expect(longBarcodeCell).toContainText(longBarcode);
  await expect(dimensionsButton).toBeVisible();

  const geometry = await linesTable.evaluate((table) => {
    const container = table.closest('.MuiTableContainer-root');
    const doc = document.documentElement;
    const body = document.body;
    const sku = table.querySelector('[data-testid="ff-inbound-line-sku"]');
    const barcode = table.querySelector('[data-testid="ff-inbound-line-barcode"]');
    const dimensionsButton = table.querySelector('[data-testid="ff-inbound-line-dimensions-edit"]');
    const skuRect = sku?.getBoundingClientRect();
    const barcodeRect = barcode?.getBoundingClientRect();
    const buttonRect = dimensionsButton?.getBoundingClientRect();

    return {
      viewportWidth: window.innerWidth,
      scrollX: window.scrollX,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      tableScrollWidth: table.scrollWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      skuClientWidth: sku?.clientWidth ?? 0,
      skuScrollWidth: sku?.scrollWidth ?? 0,
      barcodeClientWidth: barcode?.clientWidth ?? 0,
      barcodeScrollWidth: barcode?.scrollWidth ?? 0,
      skuRight: skuRect?.right ?? 0,
      barcodeRight: barcodeRect?.right ?? 0,
      buttonWidth: buttonRect?.width ?? 0,
      buttonHeight: buttonRect?.height ?? 0,
    };
  });

  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.scrollX).toBe(0);
  expect(geometry.containerClientWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.containerScrollWidth).toBeGreaterThan(geometry.containerClientWidth);
  expect(geometry.tableScrollWidth).toBeGreaterThan(geometry.containerClientWidth);
  expect(geometry.skuScrollWidth).toBeGreaterThan(geometry.skuClientWidth);
  expect(geometry.barcodeScrollWidth).toBeGreaterThan(geometry.barcodeClientWidth);
  expect(geometry.skuRight).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.barcodeRight).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.buttonWidth).toBe(40);
  expect(geometry.buttonHeight).toBe(40);
});

// TC-NEW-IN-02 — несколько коробов: отдельные кнопки, отдельное наполнение, общий скан.
test('inbound receiving v2 — multiple boxes stay independent', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-box-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 3,
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
  await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 1, expectedQty: 2 });

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
  const manualPickerSku = `sku-return-picker-${suffix}`;
  const manualPickerBarcode = `wb-return-picker-${suffix}`;
  const manualCreatedSku = `sku-return-created-${suffix}`;
  const manualCreatedBarcode = `wb-return-created-${suffix}`;
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

  const manualPickerProductRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'Return Manual Picker Product',
      sku_code: manualPickerSku,
      wb_barcode: manualPickerBarcode,
      seller_id: seed.sellerId,
      length_mm: 90,
      width_mm: 70,
      height_mm: 30,
    },
  });
  expect(manualPickerProductRes.ok()).toBeTruthy();

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
  const setPlannedBoxes = await page.request.patch(`${INBOUND_API}/${requestId}`, {
    headers: sellerHeaders,
    data: { planned_box_count: 1 },
  });
  expect(setPlannedBoxes.ok()).toBeTruthy();
  const submitReturn = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitReturn.ok()).toBeTruthy();

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
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
  await armPrintCapture(page);

  await page.getByTestId('ff-inbound-receiving-add-products').click();
  await expect(page.getByTestId('ff-inbound-picker')).toBeVisible();
  await page.getByTestId('ff-inbound-picker-search').fill(manualPickerSku);
  await page.getByTestId('ff-inbound-picker-qty').first().fill('1');
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.getByTestId('ff-inbound-picker-apply').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-picker')).toHaveCount(0);
  await page.waitForTimeout(200);
  expect(await lastCapturedPrintHtml(page)).toBe(PRINT_SENTINEL);

  const manualPickerRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({
    hasText: manualPickerSku,
  });
  await expect(manualPickerRow).toBeVisible();
  await expect(manualPickerRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('Return Created Manual Product');
  await page.getByTestId('ff-manual-product-sku').fill(manualCreatedSku);
  await page.getByTestId('ff-manual-product-barcode').fill(manualCreatedBarcode);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('40');
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);
  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  await page.waitForTimeout(200);
  expect(await lastCapturedPrintHtml(page)).toBe(PRINT_SENTINEL);

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
  const printHtml = await lastCapturedPrintHtml(page);
  expect(printHtml).toContain(factBarcode);
  expect(printHtml).not.toContain(factSku);
  await expect(page.getByTestId('marking-print-dialog')).toHaveCount(0);

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
  await page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`).click();
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  const sellerFactRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: factSku });
  await expect(sellerFactRow).toBeVisible();
  await expect(sellerFactRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText(
    'Добавлено ФФ',
  );
  await expect(sellerFactRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  await expect(sellerFactRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  await expect(sellerFactRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');
});

// TC-NEW-IN-05 — F19 negative: successful return scan without wb_barcode shows an operator error and never prints SKU.
test('inbound receiving v2 — return autoprint fails closed when scanned line has no WB barcode', async ({
  page,
}) => {
  const suffix = `rcv-return-no-wb-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const factSku = `sku-return-no-wb-${suffix}`;
  const factBarcode = `wb-return-no-wb-${suffix}`;

  const factProductRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'Return Missing WB Barcode Product',
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
  const setPlannedBoxes = await page.request.patch(`${INBOUND_API}/${requestId}`, {
    headers: sellerHeaders,
    data: { planned_box_count: 1 },
  });
  expect(setPlannedBoxes.ok()).toBeTruthy();
  const submitReturn = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitReturn.ok()).toBeTruthy();

  let scanResponseEdited = false;
  await page.route(`**${INBOUND_API}/${requestId}/receiving/scan`, async (route) => {
    if (route.request().method() !== 'POST' || scanResponseEdited) {
      await route.fallback();
      return;
    }
    scanResponseEdited = true;
    const response = await route.fetch();
    const scannedLine = (await response.json()) as Record<string, unknown>;
    await route.fulfill({
      response,
      json: { ...scannedLine, wb_barcode: null },
    });
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-return-autoprint')).toBeVisible();
  await page.getByTestId('ff-inbound-return-autoprint').click();
  await armPrintCapture(page);

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(factBarcode);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);

  await expect(page.getByTestId('ff-inbound-scan-error-snackbar')).toContainText(
    'У товара нет ШК WB для печати.',
  );
  await page.waitForTimeout(200);
  expect(await lastCapturedPrintHtml(page)).toBe(PRINT_SENTINEL);
  await expect(page.getByTestId('marking-print-dialog')).toHaveCount(0);

  const factRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: factSku });
  await expect(factRow).toBeVisible();
  await expect(factRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
});

// TC-NEW-IN-07 — селлер после проведения видит фактическую карточку: недостача, излишек и строка "Добавлено ФФ".
test('inbound receiving v2 — seller sees conducted factual card after FF shortage and added product', async ({
  page,
}) => {
  const suffix = `rcv-seller-fact-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 2,
    expectedQty: 3,
  });
  const addedSku = `ff-added-${suffix}`;
  const addedBarcode = `ff-added-barcode-${suffix}`;

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  await page.getByTestId('ff-inbound-line-manual-edit').first().click();
  await page.getByTestId('ff-inbound-line-actual').fill('2');
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
    page.getByTestId('ff-inbound-line-manual-edit').first().click(),
  ]);
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('2');

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('FF Added Seller Card Product');
  await page.getByTestId('ff-manual-product-sku').fill(addedSku);
  await page.getByTestId('ff-manual-product-barcode').fill(addedBarcode);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);
  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);

  const ffAddedRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: addedSku });
  await expect(ffAddedRow).toBeVisible();
  await expect(ffAddedRow.getByTestId('ff-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(ffAddedRow.getByTestId('ff-inbound-line-expected')).toHaveText('0');
  await expect(ffAddedRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');

  await page.getByTestId('ff-inbound-verify-complete').click();
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: seed.sku })).toContainText(
    'Недостача 1',
  );
  await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: addedSku })).toContainText(
    'Излишек 1',
  );
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  await expect(sellerDocRow).toBeVisible();
  await sellerDocRow.click();

  await expect(page.getByRole('heading', { name: /Карточка приёмки.*Поставка/ })).toBeVisible();
  await expect(page.getByText('Новая заявка на поставку', { exact: true })).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);

  await expect(page.getByTestId('seller-inbound-summary-status')).toContainText('В сортировке');
  await expect(page.getByTestId('seller-inbound-summary-operation')).toContainText('Поставка');
  await expect(page.getByTestId('seller-inbound-summary-warehouse')).toContainText('WH');
  await expect(page.getByTestId('seller-inbound-summary-boxes')).toContainText('план 2');
  await expect(page.getByTestId('seller-inbound-summary-boxes')).toContainText('факт 0');
  await expect(page.getByTestId('seller-inbound-summary-discrepancy')).toContainText('Есть расхождения');
  await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('Заявлено 3');
  await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('принято 3');

  const sellerFactLayout = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const headCells = Array.from(table.querySelectorAll('thead th'));
    const rows = Array.from(table.querySelectorAll('tbody tr[data-testid="seller-inbound-line-row"]'));
    const productIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Товар');
    const expectedIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Заявлено');
    const productWidths = rows.map((row) => row.children[productIndex]?.getBoundingClientRect().width ?? 0);
    const rowHeights = rows.map((row) => row.getBoundingClientRect().height);
    const headerBottom = Math.max(...headCells.map((cell) => cell.getBoundingClientRect().bottom));
    const firstBodyTop = rows[0]?.getBoundingClientRect().top ?? 0;
    const firstProductRight = rows[0]?.children[productIndex]?.getBoundingClientRect().right ?? 0;
    const firstExpectedLeft = rows[0]?.children[expectedIndex]?.getBoundingClientRect().left ?? 0;
    return {
      headerTexts: headCells.map((cell) => cell.textContent?.trim() ?? ''),
      headerCells: headCells.length,
      bodyCells: rows[0]?.children.length ?? 0,
      minProductWidth: Math.min(...productWidths),
      maxRowHeight: Math.max(...rowHeights),
      headerBottom,
      firstBodyTop,
      firstProductRight,
      firstExpectedLeft,
    };
  });
  expect(sellerFactLayout.headerTexts).toEqual(['Товар', 'Заявлено', 'Принято', 'Итог', '']);
  expect(sellerFactLayout.headerCells).toBe(sellerFactLayout.bodyCells);
  expect(sellerFactLayout.headerCells).toBe(5);
  expect(sellerFactLayout.minProductWidth).toBeGreaterThanOrEqual(360);
  expect(sellerFactLayout.maxRowHeight).toBeLessThanOrEqual(120);
  expect(sellerFactLayout.headerBottom).toBeLessThanOrEqual(sellerFactLayout.firstBodyTop + 1);
  expect(sellerFactLayout.firstProductRight).toBeLessThanOrEqual(sellerFactLayout.firstExpectedLeft + 1);

  const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(sellerShortageRow).toBeVisible();
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-expected')).toHaveText('3');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-actual')).toHaveText('2');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Недостача 1');

  const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  await expect(sellerAddedRow).toBeVisible();
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');

  const discrepancyTexts = await page.getByTestId('seller-inbound-line-discrepancy').allTextContents();
  expect(discrepancyTexts).not.toContain('+1');
  expect(discrepancyTexts).not.toContain('-1');
  await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);
});

// TC-NEW-IN-07 — регрессия: если справочник складов не загрузился, селлерская fact-card не показывает raw UUID.
test('inbound receiving v2 — seller factual card uses human warehouse fallback when warehouse lookup is empty', async ({
  page,
}) => {
  const suffix = `rcv-seller-wh-fallback-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  });
  const uuidPattern = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;

  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      });
      return;
    }
    await route.fallback();
  });

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  await expect(sellerDocRow).toBeVisible();
  await sellerDocRow.click();

  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);

  const warehouseSummary = page.getByTestId('seller-inbound-summary-warehouse');
  await expect(warehouseSummary).toContainText('Склад ФФ');
  await expect(warehouseSummary).not.toContainText(seed.warehouseId);
  const warehouseSummaryText = (await warehouseSummary.textContent()) ?? '';
  expect(warehouseSummaryText).not.toMatch(uuidPattern);
});

// TC-NEW-IN-06 — активная приёмка: FF создаёт новый ручной товар, он сразу попадает в факт как расхождение.
test('inbound receiving v2 — active receiving creates manual product as FF-added fact line', async ({
  page,
}) => {
  const suffix = `rcv-manual-active-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  });
  await beginInboundReceiving(page.request, adminHeaders, requestId);

  const manualSku = `manual-active-${suffix}`;
  const manualBarcode = `manual-active-barcode-${suffix}`;

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('Manual Active Receiving Product');
  await page.getByTestId('ff-manual-product-sku').fill(manualSku);
  await page.getByTestId('ff-manual-product-barcode').fill(manualBarcode);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');

  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);

  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  const factRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: manualSku });
  await expect(factRow).toBeVisible();
  await expect(factRow.getByTestId('ff-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(factRow.getByTestId('ff-inbound-line-expected')).toHaveText('0');
  await expect(factRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
});

// TC-NEW-IN-06 — негатив: если созданный товар не добавился в факт, повторная отправка привязывает тот же товар без второго create.
test('inbound receiving v2 — manual product attach failure retries without duplicate product create', async ({
  page,
}) => {
  const suffix = `rcv-manual-fail-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  });
  await beginInboundReceiving(page.request, adminHeaders, requestId);

  const manualSku = `manual-fail-${suffix}`;
  const receivingBodies: Array<{ product_id?: string; actual_qty?: number; source?: string }> = [];
  let receivingLineAttempts = 0;
  let productCreatePosts = 0;

  await page.route(`**${INBOUND_API}/**/receiving/lines`, async (route) => {
    if (route.request().method() === 'POST') {
      receivingLineAttempts += 1;
      receivingBodies.push(
        JSON.parse(route.request().postData() ?? '{}') as {
          product_id?: string;
          actual_qty?: number;
          source?: string;
        },
      );
      if (receivingLineAttempts === 1) {
        await route.fulfill({ status: 500, body: 'receiving_line_failed' });
        return;
      }
      await route.fallback();
      return;
    }
    await route.fallback();
  });
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/products')) {
      productCreatePosts += 1;
    }
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('Manual Failed Attach Product');
  await page.getByTestId('ff-manual-product-sku').fill(manualSku);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');

  await Promise.all([
    waitForPostOk(page, '/api/products'),
    page.waitForResponse(
      (r) =>
        r.url().includes('/receiving/lines') &&
        r.request().method() === 'POST' &&
        r.status() === 500,
    ),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);

  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-manual-product-error')).toContainText(
    'Товар создан, но не добавлен в факт приёмки.',
  );
  await expect(page.getByTestId('ff-manual-product-sku')).toHaveValue(manualSku);
  await expect(page.getByTestId('ff-manual-product-name')).toHaveValue('Manual Failed Attach Product');
  await expect(page.getByTestId('ff-manual-product-submit')).toContainText('Добавить в приёмку');
  expect(productCreatePosts).toBe(1);
  expect(receivingLineAttempts).toBe(1);

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);

  expect(productCreatePosts).toBe(1);
  expect(receivingLineAttempts).toBe(2);
  expect(receivingBodies).toHaveLength(2);
  expect(receivingBodies[0]).toMatchObject({ actual_qty: 1, source: 'manual_created' });
  expect(receivingBodies[1]).toMatchObject({
    product_id: receivingBodies[0].product_id,
    actual_qty: 1,
    source: 'manual_created',
  });

  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  const factRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: manualSku });
  await expect(factRow).toBeVisible();
  await expect(factRow.getByTestId('ff-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(factRow.getByTestId('ff-inbound-line-expected')).toHaveText('0');
  await expect(factRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
});

// TC-NEW-IN-06 — негатив: успешный attach закрывает диалог даже если последующий refresh детали падает.
test('inbound receiving v2 — manual product attach success closes when detail refresh fails', async ({
  page,
}) => {
  const suffix = `rcv-manual-refresh-fail-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  });
  await beginInboundReceiving(page.request, adminHeaders, requestId);

  const manualSku = `manual-refresh-fail-${suffix}`;
  const receivingBodies: Array<{ product_id?: string; actual_qty?: number; source?: string }> = [];
  let failNextDetailGet = false;
  let detailRefreshFailures = 0;
  let receivingLineAttempts = 0;
  let productCreatePosts = 0;

  await page.route(`**${INBOUND_API}/**`, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === 'POST' && pathname.endsWith('/receiving/lines')) {
      receivingLineAttempts += 1;
      receivingBodies.push(
        JSON.parse(request.postData() ?? '{}') as {
          product_id?: string;
          actual_qty?: number;
          source?: string;
        },
      );
      failNextDetailGet = true;
      await route.fallback();
      return;
    }
    if (failNextDetailGet && request.method() === 'GET' && pathname === `${INBOUND_API}/${requestId}`) {
      failNextDetailGet = false;
      detailRefreshFailures += 1;
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'detail_refresh_failed' }),
      });
      return;
    }
    await route.fallback();
  });
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/products')) {
      productCreatePosts += 1;
    }
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('Manual Refresh Failure Product');
  await page.getByTestId('ff-manual-product-sku').fill(manualSku);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');

  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/lines')),
    page.waitForResponse(
      (r) =>
        r.url().endsWith(`${INBOUND_API}/${requestId}`) &&
        r.request().method() === 'GET' &&
        r.status() === 500,
    ),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);

  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  await expect(page.getByTestId('ff-manual-product-submit')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-doc-error')).toHaveCount(0);
  expect(productCreatePosts).toBe(1);
  expect(detailRefreshFailures).toBe(1);
  expect(receivingLineAttempts).toBe(1);
  expect(receivingBodies).toHaveLength(1);
  expect(receivingBodies[0]).toMatchObject({ actual_qty: 1, source: 'manual_created' });
  await page.waitForTimeout(300);
  expect(receivingLineAttempts).toBe(1);
});

// TC-NEW-IN-04 — короб 6 шт. + ручная правка итога до 10 → PATCH loose=4, без double count.
test('inbound receiving v2 — manual edit with box saves loose not total', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `rcv-mix-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
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
