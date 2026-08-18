import fs from 'node:fs';
import path from 'node:path';

import {
  expect,
  test,
  type Locator,
  type Page,
} from '../../../../../../frontend/node_modules/@playwright/test';

import { waitForPatchOk, waitForPostOk } from '../../../../../../frontend/tests-e2e/api-waits';
import {
  INBOUND_API,
  loginFfAdmin,
  seedFfSellerInbound,
} from '../../../../../../frontend/tests-e2e/inbound-boxes-helpers';

const evidenceDir = __dirname;
const screenshotsDir = path.join(evidenceDir, 'screenshots');
const resultPath = path.join(evidenceDir, 'f03-final-result.json');
const webPort = Number(process.env.E2E_WEB_PORT ?? 18137);

type Geometry = {
  viewportWidth: number;
  documentScrollWidth: number;
  bodyScrollWidth: number;
  globalOverflowPx: number;
  tableClientWidth: number;
  tableScrollWidth: number;
  containerClientWidth: number;
  containerScrollWidth: number;
  containerScrollLeft: number;
  rowWidth: number;
  rowHeight: number;
  skuClientWidth: number;
  skuScrollWidth: number;
  barcodeClientWidth: number;
  barcodeScrollWidth: number;
  dimensionsButtonWidth: number;
  dimensionsButtonHeight: number;
  manualButtonWidth: number;
  manualButtonHeight: number;
  dimensionsButtonHitTarget: string | null;
};

const qaResult = {
  status: 'BROWSER_PRODUCT_QA_BLOCKED',
  url: `http://127.0.0.1:${webPort}/app/ff/reception`,
  command:
    'cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend && E2E_API_PORT=18136 E2E_WEB_PORT=18137 npx playwright test ../docs/reviews/product-operations-ux/2026-08-12/evidence/f03-browser-product-qa-final-current/f03-final-product-qa-current.spec.ts --config ../docs/reviews/product-operations-ux/2026-08-12/evidence/f03-browser-product-qa-final-current/playwright.f03-final-current.config.cjs --project=chromium --headed --reporter=line',
  stepsClicked: [] as string[],
  screenshots: [] as string[],
  checks: {} as Record<string, unknown>,
  geometry: {} as Record<string, Geometry>,
  responses: [] as Record<string, unknown>[],
  tests: [] as { title: string; status: string; error?: string }[],
};

function recordStep(step: string): void {
  qaResult.stepsClicked.push(step);
}

function saveResult(): void {
  fs.writeFileSync(resultPath, `${JSON.stringify(qaResult, null, 2)}\n`);
}

async function screenshot(page: Page, name: string, fullPage = false): Promise<void> {
  const rel = `screenshots/${name}`;
  await page.screenshot({ path: path.join(evidenceDir, rel), fullPage });
  qaResult.screenshots.push(rel);
  saveResult();
}

async function captureGeometry(label: string, row: Locator): Promise<Geometry> {
  const geometry = await row.evaluate((rowEl) => {
    const doc = document.documentElement;
    const body = document.body;
    const table = rowEl.closest('table');
    const container = table?.closest('.MuiTableContainer-root') as HTMLElement | null;
    const sku = rowEl.querySelector('[data-testid="ff-inbound-line-sku"]') as HTMLElement | null;
    const barcode = rowEl.querySelector('[data-testid="ff-inbound-line-barcode"]') as HTMLElement | null;
    const dimensionsButton = rowEl.querySelector(
      '[data-testid="ff-inbound-line-dimensions-edit"]',
    ) as HTMLElement | null;
    const manualButton = rowEl.querySelector(
      '[data-testid="ff-inbound-line-manual-edit"]',
    ) as HTMLElement | null;
    const rowRect = rowEl.getBoundingClientRect();
    const tableRect = table?.getBoundingClientRect();
    const dimensionsRect = dimensionsButton?.getBoundingClientRect();
    const manualRect = manualButton?.getBoundingClientRect();
    let hitTarget: string | null = null;
    if (dimensionsRect) {
      const cx = dimensionsRect.left + dimensionsRect.width / 2;
      const cy = dimensionsRect.top + dimensionsRect.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      hitTarget =
        hit?.closest('[data-testid="ff-inbound-line-dimensions-edit"]')?.getAttribute('data-testid') ??
        hit?.closest('[data-testid]')?.getAttribute('data-testid') ??
        null;
    }

    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      globalOverflowPx: Math.max(doc.scrollWidth, body.scrollWidth) - window.innerWidth,
      tableClientWidth: tableRect?.width ?? 0,
      tableScrollWidth: table?.scrollWidth ?? 0,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      containerScrollLeft: container?.scrollLeft ?? 0,
      rowWidth: rowRect.width,
      rowHeight: rowRect.height,
      skuClientWidth: sku?.clientWidth ?? 0,
      skuScrollWidth: sku?.scrollWidth ?? 0,
      barcodeClientWidth: barcode?.clientWidth ?? 0,
      barcodeScrollWidth: barcode?.scrollWidth ?? 0,
      dimensionsButtonWidth: dimensionsRect?.width ?? 0,
      dimensionsButtonHeight: dimensionsRect?.height ?? 0,
      manualButtonWidth: manualRect?.width ?? 0,
      manualButtonHeight: manualRect?.height ?? 0,
      dimensionsButtonHitTarget: hitTarget,
    };
  });
  qaResult.geometry[label] = geometry;
  saveResult();
  return geometry;
}

function expectNoGlobalOverflow(geometry: Geometry): void {
  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.globalOverflowPx).toBeLessThanOrEqual(1);
}

function expectCleanActionGeometry(geometry: Geometry): void {
  expect(geometry.dimensionsButtonWidth).toBe(40);
  expect(geometry.dimensionsButtonHeight).toBe(40);
  expect(geometry.manualButtonWidth).toBe(40);
  expect(geometry.manualButtonHeight).toBe(40);
  expect(geometry.rowHeight).toBeLessThanOrEqual(96);
}

test.beforeAll(() => {
  fs.rmSync(screenshotsDir, { recursive: true, force: true });
  fs.mkdirSync(screenshotsDir, { recursive: true });
  saveResult();
});

test.afterEach(({}, testInfo) => {
  qaResult.tests.push({
    title: testInfo.title,
    status: testInfo.status,
    error: testInfo.error?.message,
  });
  saveResult();
});

test.afterAll(() => {
  qaResult.status = qaResult.tests.every((item) => item.status === 'passed')
    ? 'BROWSER_PRODUCT_QA_PASSED'
    : 'BROWSER_PRODUCT_QA_FAILED';
  saveResult();
});

test('F03 final — same-seller catalog scan adds discrepancy and keeps row geometry stable', async ({
  page,
}) => {
  const suffix = `f03-final-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const factSku = `SKU-F03-FACT-${suffix}-`.padEnd(128, 'S');
  const factBarcode = `WB-F03-FACT-${suffix}-`.padEnd(64, '9');

  const factProductRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'F03 Final Fact Product',
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

  await page.setViewportSize({ width: 1280, height: 900 });
  await loginFfAdmin(page, seed.adminEmail, seed.password);
  recordStep('FF login');
  await page.getByTestId('nav-ff-reception').click();
  recordStep('nav-ff-reception');
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  recordStep('ff-inbound-queue-row for return request');
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Возврат');

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(factBarcode);
  const [scanResponse] = await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  recordStep('ff-inbound-receiving-scan-submit same-seller catalog barcode');
  qaResult.responses.push({
    label: 'same_seller_catalog_scan',
    status: scanResponse.status(),
    url: scanResponse.url(),
  });

  const factRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: factSku });
  const plannedRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: seed.sku });
  await expect(factRow).toBeVisible();
  await expect(factRow.getByTestId('ff-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(factRow.getByTestId('ff-inbound-line-expected')).toHaveText('0');
  await expect(factRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
  await expect(factRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Излишек 1');
  await expect(plannedRow.getByTestId('ff-inbound-line-expected')).toHaveText('1');
  await expect(plannedRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('0');
  await expect(plannedRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Недостача 1');

  qaResult.checks.sameSellerCatalogScan = {
    factSku,
    factBarcode,
    expected: '0',
    actual: '1',
    surplusVisible: 'Излишек 1',
    deficitVisible: 'Недостача 1',
    addedByFfVisible: true,
  };
  await screenshot(page, '01-desktop-same-seller-added-discrepancy.png', true);

  const desktopGeometry = await captureGeometry('desktop_1280_after_scan', factRow);
  expectNoGlobalOverflow(desktopGeometry);
  expectCleanActionGeometry(desktopGeometry);
  expect(desktopGeometry.tableScrollWidth).toBeLessThanOrEqual(desktopGeometry.containerClientWidth + 1);
  expect(desktopGeometry.skuScrollWidth).toBeGreaterThan(desktopGeometry.skuClientWidth);
  expect(desktopGeometry.barcodeScrollWidth).toBeGreaterThan(desktopGeometry.barcodeClientWidth);
  expect(desktopGeometry.dimensionsButtonHitTarget).toBe('ff-inbound-line-dimensions-edit');

  await factRow.getByTestId('ff-inbound-line-dimensions-edit').click();
  recordStep('ff-inbound-line-dimensions-edit desktop');
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toBeVisible();
  await screenshot(page, '02-desktop-dimensions-dialog-open.png');
  await page.getByTestId('ff-inbound-dimensions-length').fill('200');
  await page.getByTestId('ff-inbound-dimensions-width').fill('100');
  await page.getByTestId('ff-inbound-dimensions-height').fill('50');
  await Promise.all([
    waitForPatchOk(page, '/api/products', (u) => u.includes('/dimensions')),
    page.getByTestId('ff-inbound-dimensions-save').click(),
  ]);
  recordStep('ff-inbound-dimensions-save');
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toHaveCount(0);
  await expect(factRow.getByTestId('ff-inbound-line-dimensions')).toContainText('200×100×50 мм');
  await expect(factRow.getByTestId('ff-inbound-line-dimensions')).toContainText('1.00 л');
  await screenshot(page, '03-desktop-dimensions-saved.png', true);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  const mobileLeftGeometry = await captureGeometry('mobile_390_left_edge', factRow);
  expectNoGlobalOverflow(mobileLeftGeometry);
  expectCleanActionGeometry(mobileLeftGeometry);
  expect(mobileLeftGeometry.containerScrollWidth).toBeGreaterThan(
    mobileLeftGeometry.containerClientWidth,
  );
  expect(mobileLeftGeometry.tableScrollWidth).toBeGreaterThan(mobileLeftGeometry.containerClientWidth);
  expect(mobileLeftGeometry.skuScrollWidth).toBeGreaterThan(mobileLeftGeometry.skuClientWidth);
  expect(mobileLeftGeometry.barcodeScrollWidth).toBeGreaterThan(mobileLeftGeometry.barcodeClientWidth);
  await screenshot(page, '04-mobile-390-left-edge-no-global-overflow.png', true);

  await page.getByTestId('ff-inbound-lines-table').evaluate((table) => {
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    if (container) {
      container.scrollLeft = container.scrollWidth;
    }
  });
  await page.waitForTimeout(100);
  const mobileRightGeometry = await captureGeometry('mobile_390_right-edge-actions', factRow);
  expectNoGlobalOverflow(mobileRightGeometry);
  expectCleanActionGeometry(mobileRightGeometry);
  expect(mobileRightGeometry.containerScrollLeft).toBeGreaterThan(0);
  await screenshot(page, '05-mobile-390-right-edge-actions-clean.png', true);

  await factRow.getByTestId('ff-inbound-line-dimensions-edit').click();
  recordStep('ff-inbound-line-dimensions-edit mobile 390px');
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toBeVisible();
  await screenshot(page, '06-mobile-390-dimensions-dialog-open.png');
  await page.getByRole('button', { name: 'Отмена' }).click();
  recordStep('dimensions dialog cancel after mobile click');
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toHaveCount(0);

  qaResult.checks.overflow = {
    desktopGlobalOverflowPx: desktopGeometry.globalOverflowPx,
    mobileLeftGlobalOverflowPx: mobileLeftGeometry.globalOverflowPx,
    mobileRightGlobalOverflowPx: mobileRightGeometry.globalOverflowPx,
    mobileInternalTableOverflow: mobileLeftGeometry.containerScrollWidth > mobileLeftGeometry.containerClientWidth,
    dimensionsButtonStableDesktop: desktopGeometry.dimensionsButtonHitTarget === 'ff-inbound-line-dimensions-edit',
    dimensionsButtonStableMobileClick: true,
  };
  saveResult();
});

test('F03 final — same planned product overage is visible as red surplus', async ({ page }) => {
  const suffix = `f03-overage-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const plannedSku = `SKU-F03-OVER-${suffix}`;
  const plannedBarcode = `WB-F03-OVER-${suffix}`;

  const plannedProductRes = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'F03 Overage Product',
      sku_code: plannedSku,
      wb_barcode: plannedBarcode,
      seller_id: seed.sellerId,
      length_mm: 100,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(plannedProductRes.ok()).toBeTruthy();
  const plannedProductId = String(((await plannedProductRes.json()) as { id: string }).id);

  const sellerLogin = await page.request.post('/api/auth/login', {
    data: { email: seed.sellerEmail, password: seed.password },
  });
  expect(sellerLogin.ok()).toBeTruthy();
  const sellerToken = String(((await sellerLogin.json()) as { access_token: string }).access_token);
  const sellerHeaders = { Authorization: `Bearer ${sellerToken}` };

  const createInbound = await page.request.post(INBOUND_API, {
    headers: sellerHeaders,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(createInbound.ok()).toBeTruthy();
  const requestId = String(((await createInbound.json()) as { id: string }).id);
  const addPlannedLine = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers: sellerHeaders,
    data: { product_id: plannedProductId, expected_qty: 1 },
  });
  expect(addPlannedLine.ok()).toBeTruthy();
  const submitInbound = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitInbound.ok()).toBeTruthy();

  await page.setViewportSize({ width: 1280, height: 900 });
  await loginFfAdmin(page, seed.adminEmail, seed.password);
  recordStep('FF login for same-product overage');
  await page.getByTestId('nav-ff-reception').click();
  recordStep('nav-ff-reception for same-product overage');
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  recordStep('ff-inbound-queue-row for same-product overage request');
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  for (const scanNumber of [1, 2]) {
    await page.getByTestId('ff-inbound-receiving-scan-input').fill(plannedBarcode);
    const [scanResponse] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
      page.getByTestId('ff-inbound-receiving-scan-submit').click(),
    ]);
    recordStep(`ff-inbound-receiving-scan-submit planned product overage #${scanNumber}`);
    qaResult.responses.push({
      label: `same_product_overage_scan_${scanNumber}`,
      status: scanResponse.status(),
      url: scanResponse.url(),
    });
  }

  const overageRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: plannedSku });
  await expect(overageRow).toBeVisible();
  await expect(overageRow.getByTestId('ff-inbound-line-expected')).toHaveText('1');
  await expect(overageRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('2');
  await expect(overageRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Излишек 1');
  qaResult.checks.sameProductOverage = {
    plannedSku,
    plannedBarcode,
    expected: '1',
    actual: '2',
    surplusVisible: 'Излишек 1',
  };
  await screenshot(page, '08-desktop-same-product-overage.png', true);
  const geometry = await captureGeometry('desktop_1280_same_product_overage', overageRow);
  expectNoGlobalOverflow(geometry);
  saveResult();
});

test('F03 final — foreign barcode is forbidden with human message', async ({ page }) => {
  const suffix = `f03-foreign-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const adminHeaders = { Authorization: `Bearer ${seed.token}` };
  const foreignBarcode = `WB-F03-FOREIGN-${suffix}`.slice(0, 64);

  const otherSeller = await page.request.post('/api/sellers', {
    headers: adminHeaders,
    data: { name: `F03 Foreign Seller ${suffix}` },
  });
  expect(otherSeller.ok()).toBeTruthy();
  const otherSellerId = String(((await otherSeller.json()) as { id: string }).id);
  const foreignProduct = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'F03 Foreign Product',
      sku_code: `SKU-F03-FOREIGN-${suffix}`,
      wb_barcode: foreignBarcode,
      seller_id: otherSellerId,
      length_mm: 100,
      width_mm: 80,
      height_mm: 40,
    },
  });
  expect(foreignProduct.ok()).toBeTruthy();

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
  recordStep('FF login for foreign barcode negative');
  await page.getByTestId('nav-ff-reception').click();
  recordStep('nav-ff-reception for foreign barcode negative');
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  recordStep('ff-inbound-queue-row for foreign barcode request');
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await page.getByTestId('ff-inbound-receiving-scan-input').fill(foreignBarcode);
  const [scanResponse] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes('/receiving/scan') &&
        r.request().method() === 'POST' &&
        r.status() === 422,
    ),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
  recordStep('ff-inbound-receiving-scan-submit foreign seller barcode');
  const body = await scanResponse.text();
  const snackbar = page.getByTestId('ff-inbound-scan-error-snackbar');
  await expect(snackbar).toContainText('Товар не найден в этой поставке');
  const visibleBody = await page.locator('body').innerText();
  expect(visibleBody).not.toContain('product_not_on_request');
  expect(visibleBody).not.toContain('product_seller_mismatch');
  expect(visibleBody).not.toContain('"detail"');
  await screenshot(page, '07-foreign-barcode-human-message.png', true);

  qaResult.responses.push({
    label: 'foreign_seller_barcode_scan',
    status: scanResponse.status(),
    responseBody: body,
    humanMessage: await snackbar.innerText(),
  });
  qaResult.checks.foreignBarcode = {
    foreignBarcode,
    forbidden: scanResponse.status() === 422,
    humanMessageVisible: true,
    rawCodeHiddenFromUi: true,
  };
  saveResult();
});
