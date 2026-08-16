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

const UNIFIED_COLUMN_HEADERS = [
  'Фото',
  'Артикул',
  'ШК',
  'Артикул продавца',
  'Артикул WB',
  'Наименование',
  'Кол-во',
  'Печать',
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

// BL-2: read-only statuses must render the exact same document form as the draft
// (identity columns visible, no compact "micro-table"). Availability of actions is
// the only thing allowed to change; the table shape must not.
async function expectUnifiedTableGeometry(page: Page): Promise<void> {
  const geometry = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const doc = document.documentElement;
    const body = document.body;
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const headCells = Array.from(table.querySelectorAll('thead th'));
    const rows = Array.from(table.querySelectorAll('tbody tr[data-testid="seller-inbound-line-row"]'));
    return {
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      viewportWidth: window.innerWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      headerTexts: headCells.map((cell) => cell.textContent?.trim() ?? ''),
      headerCells: headCells.length,
      bodyCells: rows[0]?.children.length ?? 0,
    };
  });

  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.headerTexts.slice(0, UNIFIED_COLUMN_HEADERS.length)).toEqual([
    ...UNIFIED_COLUMN_HEADERS,
  ]);
  expect(geometry.headerCells).toBe(9);
  expect(geometry.headerCells).toBe(geometry.bodyCells);
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

  // Same document form as the draft — not a compact report table.
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible();
  for (const header of UNIFIED_COLUMN_HEADERS) {
    await expect(page.getByRole('columnheader', { name: header })).toBeVisible();
  }
  await expectUnifiedTableGeometry(page);

  // Actions unavailable in this status disappear rather than reshaping the form.
  await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-fact-summary')).toHaveCount(0);
  await expect(page.getByText('Итог приемки')).toHaveCount(0);
  await expect(page.getByText('Что не так')).toHaveCount(0);

  const visibleRows = page.getByTestId('seller-inbound-line-row');
  await expect(visibleRows).toHaveCount(2);

  const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-qty')).toHaveValue('3');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-qty')).toBeDisabled();
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-fact')).toContainText('Принято: 2');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-fact')).toContainText('Недостача 1');

  const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-qty')).toHaveValue('0');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-fact')).toContainText('Принято: 1');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-fact')).toContainText('Излишек 1');
}

async function expectCleanFactCardReadBack(
  page: Page,
  seed: Awaited<ReturnType<typeof seedFfSellerInbound>>,
  requestId: string,
): Promise<void> {
  await expectSellerShellOnInbound(page, requestId);
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-fact-summary')).toHaveCount(0);
  await expect(page.getByText('Итог приемки')).toHaveCount(0);
  await expect(page.getByText('Что не так')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-added-by-ff')).toHaveCount(0);

  await expectUnifiedTableGeometry(page);

  const cleanRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(cleanRow).toBeVisible();
  await expect(cleanRow.getByTestId('seller-inbound-line-qty')).toHaveValue('2');
  await expect(cleanRow.getByTestId('seller-inbound-line-fact')).toContainText('Принято: 2');
  await expect(cleanRow.getByTestId('seller-inbound-line-fact')).toContainText('ОК');
}

// TC-NEW-IN-07 — seller reads back the same document form after FF posted a discrepancy
// (shortage + FF-added line), with actions disabled/hidden instead of a different layout.
test('seller inbound document keeps the same form after a discrepancy at 1280px', async ({ page }) => {
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
    data: { product_id: addedProductId, actual_qty: 1, source: 'seller_catalog' },
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

// TC-NEW-IN-07 — clean acceptance (no discrepancy) still renders the same document form,
// with normal rows undecorated, and survives reload read-back.
test('seller inbound document shows clean acceptance in the same form', async ({ page }) => {
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
