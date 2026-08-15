import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  loginFfAdmin,
  loginSellerPortal,
  seedFfSellerInbound,
  sellerPath,
} from './inbound-boxes-helpers';

test.describe.configure({ timeout: 120_000 });

// TC-NEW-F18-001 / TC-NEW-F18-002 / TC-NEW-F18-003 / TC-NEW-F18-004 / TC-NEW-F18-005 —
// seller UI creates supply and return drafts; labels survive seller list, FF queue/card, print heading, and page-contained draft table layout.
test('seller chooses supply or return before inbound draft creation', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `f18-op-${Date.now()}`);
  const returnSku = `f18-return-sku-${seed.suffix}`;
  const returnBarcode = `f18-return-barcode-${seed.suffix}`;
  const returnProduct = await page.request.post('/api/products', {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: {
      name: 'F18 Return Product',
      sku_code: returnSku,
      wb_barcode: returnBarcode,
      seller_id: seed.sellerId,
      length_mm: 100,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(returnProduct.ok()).toBeTruthy();
  const todayIso = new Date().toISOString().slice(0, 10);
  const otherSeller = await page.request.post('/api/sellers', {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: { name: `F18 Other Seller ${seed.suffix}` },
  });
  expect(otherSeller.ok()).toBeTruthy();
  const otherSellerId = String(((await otherSeller.json()) as { id: string }).id);
  const otherProduct = await page.request.post('/api/products', {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: {
      name: `F18 Other Hidden Product ${seed.suffix}`,
      sku_code: `f18-other-hidden-${seed.suffix}`,
      wb_barcode: `f18-other-hidden-barcode-${seed.suffix}`,
      seller_id: otherSellerId,
      length_mm: 100,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(otherProduct.ok()).toBeTruthy();
  const hiddenWaybill = `HIDDEN-${seed.suffix}`;
  const hiddenInbound = await page.request.post(INBOUND_API, {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: {
      warehouse_id: seed.warehouseId,
      planned_delivery_date: todayIso,
      waybill_number: hiddenWaybill,
    },
  });
  expect(hiddenInbound.ok()).toBeTruthy();
  const hiddenInboundId = String(((await hiddenInbound.json()) as { id: string }).id);
  const hiddenLine = await page.request.post(`${INBOUND_API}/${hiddenInboundId}/lines`, {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: { product_id: String(((await otherProduct.json()) as { id: string }).id), expected_qty: 7 },
  });
  expect(hiddenLine.ok()).toBeTruthy();

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await expect(page.getByTestId('seller-documents-list')).not.toContainText(hiddenWaybill);
  await expect(page.getByTestId('seller-shipments-empty')).toContainText(
    'На сегодня и завтра нет ваших документов с плановой датой',
  );
  await expect(page.getByTestId('seller-create-inbound')).toContainText('Создать заявку на поставку');
  await expect(page.getByTestId('seller-create-return')).toContainText('Создать заявку на возврат');

  const [supplyCreate] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('seller-create-inbound').click(),
  ]);
  const supplyPostBody = JSON.parse(supplyCreate.request().postData() ?? '{}') as {
    operation_type?: string;
  };
  expect(supplyPostBody.operation_type).toBe('inbound');
  const supply = (await supplyCreate.json()) as { id: string; operation_type: string };
  expect(supply.operation_type).toBe('inbound');
  await expect(page.getByRole('heading', { name: 'Новая заявка на поставку' })).toBeVisible();
  await expect(page.getByTestId('seller-inbound-operation-type')).toContainText('Поставка');
  await expect(page.getByTestId('seller-inbound-operation-toggle')).toHaveCount(0);
  await page.getByTestId('seller-inbound-planned-boxes').fill('1');
  await page.getByTestId('seller-inbound-save-draft').click();
  await expect(page.getByTestId('seller-inbound-draft-ok')).toContainText('Заявка сохранена');
  await page.getByTestId('seller-inbound-close').click();
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await expect(page.getByTestId('seller-shipments-today')).toContainText('Поставка');
  await expect(page.getByTestId('seller-shipments-calendar')).not.toContainText(hiddenWaybill);

  const [returnCreate] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('seller-create-return').click(),
  ]);
  const returnPostBody = JSON.parse(returnCreate.request().postData() ?? '{}') as {
    operation_type?: string;
  };
  expect(returnPostBody.operation_type).toBe('return');
  const returnDraft = (await returnCreate.json()) as { id: string; operation_type: string };
  expect(returnDraft.operation_type).toBe('return');
  await expect(page.getByRole('heading', { name: 'Новая заявка на возврат' })).toBeVisible();
  await expect(page.getByTestId('seller-inbound-operation-type')).toContainText('Возврат');
  await expect(page.locator('body')).not.toContainText('operation_type');
  await expect(page.locator('body')).not.toContainText(/\breturn\b/);
  expect(page.url()).toContain(sellerPath('/inbound/new'));
  expect(page.url()).not.toContain('/returns');
  await page.setViewportSize({ width: 1024, height: 768 });

  await page.getByTestId('seller-inbound-add-products').click();
  await expect(page.getByTestId('seller-inbound-picker')).toBeVisible();
  await page.getByTestId('seller-inbound-picker-search').fill(`missing-${returnBarcode}`);
  await page.getByTestId('seller-inbound-picker-search').press('Enter');
  await expect(page.getByTestId('seller-inbound-picker-error')).toContainText(
    'Товар с таким штрихкодом не найден в каталоге',
  );
  await page.getByTestId('seller-inbound-picker-search').fill(returnBarcode);
  await page.getByTestId('seller-inbound-picker-search').press('Enter');
  await expect(page.getByTestId('seller-inbound-picker-qty').first()).toHaveValue('1');
  await page.getByTestId('seller-inbound-picker-search').fill(returnSku);
  await page.getByTestId('seller-inbound-picker-select-all').click();
  await page.getByTestId('seller-inbound-picker-bulk-qty').fill('2');
  await page.getByTestId('seller-inbound-picker-bulk-apply').click();
  await expect(page.getByTestId('seller-inbound-picker-qty').first()).toHaveValue('2');
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines')),
    page.getByTestId('seller-inbound-picker-apply').click(),
  ]);
  await expect(page.getByTestId('seller-inbound-picker')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-row')).toHaveCount(1);
  await expect(page.getByTestId('seller-inbound-line-row')).toContainText('F18 Return Product');

  const draftLayout = await page.getByTestId('seller-inbound-draft-form').evaluate((form) => {
    const table = form.querySelector('[data-testid="seller-inbound-lines-table"]') as HTMLElement | null;
    if (!table) {
      throw new Error('seller inbound draft table not found');
    }
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const headCells = Array.from(table.querySelectorAll('thead th')) as HTMLElement[];
    const row = table.querySelector('tbody tr[data-testid="seller-inbound-line-row"]') as HTMLElement | null;
    if (!row) {
      throw new Error('seller inbound draft row not found');
    }
    const nameIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Наименование');
    const qtyIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Кол-во');
    const nameCell = row.children[nameIndex] as HTMLElement | undefined;
    const qtyCell = row.children[qtyIndex] as HTMLElement | undefined;
    const rowRect = row.getBoundingClientRect();
    const nameRect = nameCell?.getBoundingClientRect();
    const qtyRect = qtyCell?.getBoundingClientRect();
    const headerBottom = Math.max(...headCells.map((cell) => cell.getBoundingClientRect().bottom));
    const firstBodyTop = rowRect.top;
    return {
      headerCells: headCells.length,
      bodyCells: row.children.length,
      nameText: nameCell?.textContent ?? '',
      nameWidth: nameRect?.width ?? 0,
      rowHeight: rowRect.height,
      headerBottom,
      firstBodyTop,
      nameRight: nameRect?.right ?? 0,
      qtyLeft: qtyRect?.left ?? 0,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
    };
  });
  expect(draftLayout.headerCells).toBe(9);
  expect(draftLayout.bodyCells).toBe(9);
  expect(draftLayout.nameText).toContain('F18 Return Product');
  expect(draftLayout.nameWidth).toBeGreaterThanOrEqual(250);
  expect(draftLayout.rowHeight).toBeLessThanOrEqual(96);
  expect(draftLayout.headerBottom).toBeLessThanOrEqual(draftLayout.firstBodyTop + 1);
  expect(draftLayout.nameRight).toBeLessThanOrEqual(draftLayout.qtyLeft + 1);
  expect(draftLayout.containerScrollWidth).toBeGreaterThanOrEqual(draftLayout.containerClientWidth);
  expect(draftLayout.containerScrollWidth).toBeGreaterThanOrEqual(1096);

  await page.setViewportSize({ width: 1280, height: 720 });
  const returnDraftOverflow = await page.getByTestId('seller-inbound-draft-form').evaluate((form) => {
    const table = form.querySelector('[data-testid="seller-inbound-lines-table"]') as HTMLElement | null;
    if (!table) {
      throw new Error('seller inbound draft table not found');
    }
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const appRoot = document.querySelector(
      '[data-testid="app-root"], [data-testid="app-frame"]',
    ) as HTMLElement | null;
    const doc = document.documentElement;
    const body = document.body;
    return {
      viewportWidth: window.innerWidth,
      scrollX: window.scrollX,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      appRootScrollWidth: appRoot?.scrollWidth ?? 0,
      appRootClientWidth: appRoot?.clientWidth ?? 0,
      tableScrollWidth: table.scrollWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
    };
  });
  expect(returnDraftOverflow.documentScrollWidth).toBeLessThanOrEqual(
    returnDraftOverflow.viewportWidth + 1,
  );
  expect(returnDraftOverflow.bodyScrollWidth).toBeLessThanOrEqual(
    returnDraftOverflow.viewportWidth + 1,
  );
  expect(returnDraftOverflow.appRootScrollWidth).toBeLessThanOrEqual(
    returnDraftOverflow.viewportWidth + 1,
  );
  expect(returnDraftOverflow.appRootClientWidth).toBeLessThanOrEqual(
    returnDraftOverflow.viewportWidth + 1,
  );
  expect(returnDraftOverflow.scrollX).toBe(0);
  expect(returnDraftOverflow.containerClientWidth).toBeLessThanOrEqual(
    returnDraftOverflow.viewportWidth,
  );
  expect(returnDraftOverflow.containerScrollWidth).toBeGreaterThan(
    returnDraftOverflow.containerClientWidth,
  );
  expect(returnDraftOverflow.tableScrollWidth).toBeGreaterThan(
    returnDraftOverflow.containerClientWidth,
  );

  await page.getByTestId('seller-inbound-line-print-barcode').click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-product-label-preview')).toContainText(returnBarcode);
  await expect(page.getByTestId('ff-product-label-qty')).toHaveValue('1');
  await page.getByTestId('ff-product-label-cancel').click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toHaveCount(0);

  await page.getByTestId('seller-inbound-waybill-number').fill(`WAYBILL-${seed.suffix}`);
  await page.getByTestId('seller-inbound-planned-boxes').fill('0');
  await page.getByTestId('seller-inbound-submit-warehouse').click();
  await expect(page.getByTestId('seller-inbound-draft-error')).toContainText('Укажите количество грузомест');
  await page.getByTestId('seller-inbound-planned-boxes').fill('2');
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/submit')),
    page.getByTestId('seller-inbound-submit-warehouse').click(),
  ]);

  const supplyRow = page.locator(
    `[data-testid="seller-documents-row"][data-doc-id="${supply.id}"]`,
  );
  const returnRow = page.locator(
    `[data-testid="seller-documents-row"][data-doc-id="${returnDraft.id}"]`,
  );
  await expect(supplyRow).toContainText('Поставка');
  await expect(returnRow).toContainText('Возврат');
  await expect(returnRow).toContainText(`WAYBILL-${seed.suffix}`);
  await expect(returnRow).toHaveAttribute('data-doc-operation-type', 'return');

  await page.getByTestId('seller-documents-type').click();
  await page.getByRole('option', { name: 'Возврат' }).click();
  await expect(returnRow).toBeVisible();
  await expect(supplyRow).toHaveCount(0);

  await page.getByTestId('seller-documents-type').click();
  await page.getByRole('option', { name: 'Поставка' }).click();
  await expect(supplyRow).toBeVisible();
  await expect(returnRow).toHaveCount(0);

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-inbound-create-return')).toContainText('Создать возврат');
  const [ffCreateReturn] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('ff-inbound-create-return').click(),
  ]);
  const ffCreateReturnBody = JSON.parse(ffCreateReturn.request().postData() ?? '{}') as {
    operation_type?: string;
  };
  expect(ffCreateReturnBody.operation_type).toBe('return');
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Возврат');
  await page.getByTestId('ff-doc-dialog-close').click();
  await expect(page.getByTestId('ff-doc-dialog')).toHaveCount(0);
  await page.getByTestId('nav-ff-reception').click();
  const ffReturnRow = page.locator(
    `[data-testid="ff-inbound-queue-row"][data-request-id="${returnDraft.id}"]`,
  );
  await expect(ffReturnRow.getByTestId('ff-inbound-queue-document')).toContainText('Возврат');
  await expect(ffReturnRow.getByTestId('ff-inbound-queue-waybill-number')).toContainText(
    `WAYBILL-${seed.suffix}`,
  );
  await ffReturnRow.click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Возврат');
  await expect(page.getByTestId('ff-inbound-waybill-number')).toContainText(`WAYBILL-${seed.suffix}`);
  const returnDocumentNumber =
    (await page.getByTestId('ff-inbound-document-number').textContent())?.trim() ?? '';
  expect(returnDocumentNumber).toContain('№');

  await expect(page.getByTestId('ff-inbound-print-waybill')).toHaveCount(0);
});
