import { expect, test, type Page } from '@playwright/test';

import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  loginSellerPortal,
  seedFfSellerInbound,
  sellerPath,
} from './inbound-boxes-helpers';

type InboundDetail = {
  lines: { id: string; product_id: string }[];
};

const OLD_REPORT_COLUMN_HEADERS = [
  'Фото',
  'Артикул',
  'ШК',
  'Артикул продавца',
  'Артикул WB',
  'Наименование',
  'Расхождение',
] as const;

async function createFfAddedProduct(
  page: Page,
  seed: Awaited<ReturnType<typeof seedFfSellerInbound>>,
  sku: string,
): Promise<string> {
  const res = await page.request.post('/api/products', {
    headers: { Authorization: `Bearer ${seed.token}` },
    data: {
      name: 'F05 Geometry Added Product',
      sku_code: sku,
      wb_barcode: `${sku}-barcode`,
      length_mm: 100,
      width_mm: 80,
      height_mm: 50,
      seller_id: seed.sellerId,
    },
  });
  expect(res.ok()).toBeTruthy();
  return String(((await res.json()) as { id: string }).id);
}

async function expectCompactTableGeometry(page: Page): Promise<void> {
  const geometry = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const doc = document.documentElement;
    const body = document.body;
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const headCells = Array.from(table.querySelectorAll('thead th'));
    const rows = Array.from(table.querySelectorAll('tbody tr[data-testid="seller-inbound-line-row"]'));
    const productIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Товар');
    const expectedIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Заявлено');
    const containerRect = container?.getBoundingClientRect();
    const productWidths = rows.map((row) => row.children[productIndex]?.getBoundingClientRect().width ?? 0);
    const rowHeights = rows.map((row) => row.getBoundingClientRect().height);
    const headerBottom = Math.max(...headCells.map((cell) => cell.getBoundingClientRect().bottom));
    const firstBodyTop = rows[0]?.getBoundingClientRect().top ?? 0;
    const firstProductRight = rows[0]?.children[productIndex]?.getBoundingClientRect().right ?? 0;
    const firstExpectedLeft = rows[0]?.children[expectedIndex]?.getBoundingClientRect().left ?? 0;
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      containerRight: containerRect?.right ?? 0,
      lastHeaderRight: headCells[headCells.length - 1]?.getBoundingClientRect().right ?? 0,
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

  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.containerScrollWidth).toBeLessThanOrEqual(geometry.containerClientWidth + 1);
  expect(geometry.lastHeaderRight).toBeLessThanOrEqual(geometry.containerRight + 1);
  expect(geometry.headerTexts).toEqual(['Товар', 'Заявлено', 'Принято', 'Итог', '']);
  expect(geometry.headerCells).toBe(geometry.bodyCells);
  expect(geometry.headerCells).toBe(5);
  expect(geometry.minProductWidth).toBeGreaterThanOrEqual(360);
  expect(geometry.maxRowHeight).toBeLessThanOrEqual(120);
  expect(geometry.headerBottom).toBeLessThanOrEqual(geometry.firstBodyTop + 1);
  expect(geometry.firstProductRight).toBeLessThanOrEqual(geometry.firstExpectedLeft + 1);
}

async function expectSellerShellOnInbound(page: Page, requestId: string): Promise<void> {
  await expect(page).toHaveTitle('WMS · Селлер');
  await expect(page.getByTestId('app-topbar')).toContainText('Портал селлера');
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible();
  expect(new URL(page.url()).pathname).toBe(sellerPath(`/inbound/${requestId}`));
}

async function expectDiscrepancyFactCardReadBack(
  page: Page,
  seed: Awaited<ReturnType<typeof seedFfSellerInbound>>,
  addedSku: string,
  requestId: string,
): Promise<void> {
  await expectSellerShellOnInbound(page, requestId);
  await expect(page.getByRole('heading', { name: /Карточка приёмки.*Поставка/ })).toBeVisible();
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);

  await expect(page.getByTestId('seller-inbound-fact-summary')).toHaveCount(0);
  await expect(page.getByText('Итог приемки')).toHaveCount(0);
  await expect(page.getByText('Что не так')).toHaveCount(0);
  for (const header of OLD_REPORT_COLUMN_HEADERS) {
    await expect(page.getByRole('columnheader', { name: header })).toHaveCount(0);
  }

  await expectCompactTableGeometry(page);

  const visibleRows = page.getByTestId('seller-inbound-line-row');
  await expect(visibleRows).toHaveCount(2);
  await expect(visibleRows.first()).toContainText(addedSku);
  await expect(visibleRows.nth(1)).toContainText(seed.sku);

  const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-expected')).toHaveText('3');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-actual')).toHaveText('2');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Недостача 1');

  const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');

  await expect(page.getByTestId('seller-inbound-line-details')).toHaveCount(0);
  await sellerAddedRow.getByTestId('seller-inbound-line-expand').click();
  const details = page.getByTestId('seller-inbound-line-details');
  await expect(details).toBeVisible();
  await expect(details).toContainText('Артикул');
  await expect(details).toContainText(addedSku);
  await expect(details).toContainText('ШК');
  await expect(details).toContainText(`${addedSku}-barcode`);
  await expect(details).toContainText('Артикул продавца');
  await expect(details).toContainText('Артикул WB');
  await sellerAddedRow.getByTestId('seller-inbound-line-expand').click();
  await expect(page.getByTestId('seller-inbound-line-details')).toHaveCount(0);
}

async function expectCleanFactCardReadBack(
  page: Page,
  seed: Awaited<ReturnType<typeof seedFfSellerInbound>>,
  requestId: string,
): Promise<void> {
  await expectSellerShellOnInbound(page, requestId);
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-fact-summary')).toHaveCount(0);
  await expect(page.getByText('Итог приемки')).toHaveCount(0);
  await expect(page.getByText('Что не так')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-summary-boxes')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-added-by-ff')).toHaveCount(0);

  const cleanRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(cleanRow).toBeVisible();
  await expect(cleanRow.getByTestId('seller-inbound-line-expected')).toHaveText('2');
  await expect(cleanRow.getByTestId('seller-inbound-line-actual')).toHaveText('2');
  await expect(cleanRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('ОК');

  const geometry = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const row = table.querySelector('tbody tr[data-testid="seller-inbound-line-row"]');
    return {
      headerTexts: Array.from(table.querySelectorAll('thead th')).map((cell) => cell.textContent?.trim() ?? ''),
      rowBackground: row ? window.getComputedStyle(row).backgroundColor : '',
    };
  });
  expect(geometry.headerTexts).toEqual(['Товар', 'Заявлено', 'Принято', 'Итог', '']);
  expect(geometry.rowBackground).toBe('rgba(46, 125, 50, 0.08)');
}

// TC-NEW-IN-07 — seller fact-card at 1280px shows outcome/problem summary, 5 working columns, FF-added marker, local details, and reload read-back.
test('seller inbound fact-card keeps a compact working discrepancy card at 1280px', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const suffix = `f05-geometry-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 2,
    expectedQty: 3,
  });
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };

  await beginInboundReceiving(page.request, adminHeaders, requestId);
  const detailRes = await page.request.get(`${INBOUND_API}/${requestId}`, { headers: adminHeaders });
  expect(detailRes.ok()).toBeTruthy();
  const detail = (await detailRes.json()) as InboundDetail;
  const plannedLineId = detail.lines.find((line) => line.product_id === seed.productId)?.id;
  expect(plannedLineId).toBeTruthy();

  const shortage = await page.request.patch(`${INBOUND_API}/${requestId}/lines/${plannedLineId}/actual`, {
    headers: { ...adminHeaders, 'Content-Type': 'application/json' },
    data: { actual_qty: 2 },
  });
  expect(shortage.ok()).toBeTruthy();

  const addedSku = `ff-added-${suffix}`;
  const addedProductId = await createFfAddedProduct(page, seed, addedSku);
  const addedLine = await page.request.post(`${INBOUND_API}/${requestId}/receiving/lines`, {
    headers: { ...adminHeaders, 'Content-Type': 'application/json' },
    data: { product_id: addedProductId, actual_qty: 1, source: 'manual_created' },
  });
  expect(addedLine.ok()).toBeTruthy();

  const complete = await page.request.post(`${INBOUND_API}/${requestId}/complete-receiving`, {
    headers: adminHeaders,
  });
  expect(complete.ok()).toBeTruthy();

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  await expect(sellerDocRow).toBeVisible();
  await sellerDocRow.click();

  await expectDiscrepancyFactCardReadBack(page, seed, addedSku, requestId);
  await page.reload();
  await expectDiscrepancyFactCardReadBack(page, seed, addedSku, requestId);
  await page.getByTestId('nav-seller-documents').click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(sellerPath('/documents'));
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await expect(sellerDocRow).toBeVisible();
});

// TC-NEW-IN-07 — seller fact-card clean state shows "Без расхождений", keeps normal rows undecorated, and survives reload read-back.
test('seller inbound fact-card shows clean acceptance without problem noise', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const suffix = `f05-clean-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 2,
  });
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };

  await beginInboundReceiving(page.request, adminHeaders, requestId);
  const detailRes = await page.request.get(`${INBOUND_API}/${requestId}`, { headers: adminHeaders });
  expect(detailRes.ok()).toBeTruthy();
  const detail = (await detailRes.json()) as InboundDetail;
  const plannedLineId = detail.lines.find((line) => line.product_id === seed.productId)?.id;
  expect(plannedLineId).toBeTruthy();

  const accepted = await page.request.patch(`${INBOUND_API}/${requestId}/lines/${plannedLineId}/actual`, {
    headers: { ...adminHeaders, 'Content-Type': 'application/json' },
    data: { actual_qty: 2 },
  });
  expect(accepted.ok()).toBeTruthy();
  const complete = await page.request.post(`${INBOUND_API}/${requestId}/complete-receiving`, {
    headers: adminHeaders,
  });
  expect(complete.ok()).toBeTruthy();

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  await expect(sellerDocRow).toBeVisible();
  await sellerDocRow.click();

  await expectCleanFactCardReadBack(page, seed, requestId);
  await page.reload();
  await expectCleanFactCardReadBack(page, seed, requestId);
});
