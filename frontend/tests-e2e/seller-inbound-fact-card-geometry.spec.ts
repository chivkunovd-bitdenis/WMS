import { expect, test, type Page } from '@playwright/test';

import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  loginSellerPortal,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

type InboundDetail = {
  lines: { id: string; product_id: string }[];
};

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

// TC-NEW-IN-07 — seller fact-card at 1280px shows expected/fact/discrepancy/FF-added without horizontal scroll.
test('seller inbound fact-card keeps discrepancy visible at 1280px', async ({ page }) => {
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

  await expect(page.getByRole('heading', { name: /Карточка приёмки.*Поставка/ })).toBeVisible();
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);

  const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-expected')).toHaveText('3');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-actual')).toHaveText('2');
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Недостача 1');

  const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');

  const geometry = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const doc = document.documentElement;
    const body = document.body;
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const headCells = Array.from(table.querySelectorAll('thead th'));
    const rows = Array.from(table.querySelectorAll('tbody tr[data-testid="seller-inbound-line-row"]'));
    const nameIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Наименование');
    const expectedIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Заявлено');
    const discrepancyIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Расхождение');
    const containerRect = container?.getBoundingClientRect();
    const nameWidths = rows.map((row) => row.children[nameIndex]?.getBoundingClientRect().width ?? 0);
    const rowHeights = rows.map((row) => row.getBoundingClientRect().height);
    const headerBottom = Math.max(...headCells.map((cell) => cell.getBoundingClientRect().bottom));
    const firstBodyTop = rows[0]?.getBoundingClientRect().top ?? 0;
    const firstNameRight = rows[0]?.children[nameIndex]?.getBoundingClientRect().right ?? 0;
    const firstExpectedLeft = rows[0]?.children[expectedIndex]?.getBoundingClientRect().left ?? 0;
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      containerRight: containerRect?.right ?? 0,
      discrepancyHeaderRight: headCells[discrepancyIndex]?.getBoundingClientRect().right ?? 0,
      headerCells: headCells.length,
      bodyCells: rows[0]?.children.length ?? 0,
      minNameWidth: Math.min(...nameWidths),
      maxRowHeight: Math.max(...rowHeights),
      headerBottom,
      firstBodyTop,
      firstNameRight,
      firstExpectedLeft,
    };
  });

  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.containerScrollWidth).toBeLessThanOrEqual(geometry.containerClientWidth + 1);
  expect(geometry.discrepancyHeaderRight).toBeLessThanOrEqual(geometry.containerRight + 1);
  expect(geometry.headerCells).toBe(geometry.bodyCells);
  expect(geometry.minNameWidth).toBeGreaterThanOrEqual(240);
  expect(geometry.maxRowHeight).toBeLessThanOrEqual(120);
  expect(geometry.headerBottom).toBeLessThanOrEqual(geometry.firstBodyTop + 1);
  expect(geometry.firstNameRight).toBeLessThanOrEqual(geometry.firstExpectedLeft + 1);
});
