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
  loginSellerPortal,
  seedFfSellerInbound,
} from '../../../../../../frontend/tests-e2e/inbound-boxes-helpers';

const evidenceDir = __dirname;
const screenshotsDir = path.join(evidenceDir, 'screenshots');
const resultPath = path.join(evidenceDir, 'f05-final-current-result.json');
const webPort = Number(process.env.E2E_WEB_PORT ?? 18147);

type Geometry = {
  viewportWidth: number;
  documentScrollWidth: number;
  bodyScrollWidth: number;
  globalOverflowPx: number;
  tableClientWidth: number;
  tableScrollWidth: number;
  containerClientWidth: number;
  containerScrollWidth: number;
  containerLeft: number;
  containerRight: number;
  headerCells: number;
  bodyCells: number;
  minNameWidth: number;
  maxRowHeight: number;
  headerBottom: number;
  firstBodyTop: number;
  firstNameRight: number;
  firstExpectedLeft: number;
  discrepancyHeaderLeft: number;
  discrepancyHeaderRight: number;
  visibleButtonTexts: string[];
};

const qaResult = {
  status: 'BROWSER_PRODUCT_QA_BLOCKED',
  testedUrl: `http://127.0.0.1:${webPort}`,
  command:
    'cd /Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend && E2E_API_PORT=18146 E2E_WEB_PORT=18147 npx playwright test ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-final-current/f05-browser-product-qa-final-current.spec.ts --config ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-final-current/playwright.f05-final-current.config.cjs --project=chromium --headed --reporter=line',
  requestId: '',
  expectedSku: '',
  addedSku: '',
  stepsClicked: [] as string[],
  screenshots: [] as string[],
  checks: {} as Record<string, unknown>,
  geometry: {} as Record<string, Geometry>,
  tests: [] as { title: string; status: string; error?: string }[],
};

function recordStep(step: string): void {
  qaResult.stepsClicked.push(step);
  saveResult();
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

async function sellerToken(page: Page, email: string, password: string): Promise<string> {
  const login = await page.request.post('/api/auth/login', {
    data: { email, password },
  });
  expect(login.ok()).toBeTruthy();
  return String(((await login.json()) as { access_token: string }).access_token);
}

async function createSubmittedInbound(
  page: Page,
  seed: Awaited<ReturnType<typeof seedFfSellerInbound>>,
  opts: { plannedBoxes: number; expectedQty: number },
): Promise<string> {
  const token = await sellerToken(page, seed.sellerEmail, seed.password);
  const headers = { Authorization: `Bearer ${token}` };

  const create = await page.request.post(INBOUND_API, {
    headers,
    data: { warehouse_id: seed.warehouseId },
  });
  expect(create.ok()).toBeTruthy();
  const requestId = String(((await create.json()) as { id: string }).id);

  const patch = await page.request.patch(`${INBOUND_API}/${requestId}`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { planned_box_count: opts.plannedBoxes },
  });
  expect(patch.ok()).toBeTruthy();

  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { product_id: seed.productId, expected_qty: opts.expectedQty },
  });
  expect(line.ok()).toBeTruthy();

  const submit = await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers });
  expect(submit.ok()).toBeTruthy();

  return requestId;
}

async function scanInboundSku(page: Page, sku: string): Promise<void> {
  await page.getByTestId('ff-inbound-receiving-scan-input').fill(sku);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
    page.getByTestId('ff-inbound-receiving-scan-submit').click(),
  ]);
}

async function visibleText(locator: Locator): Promise<string> {
  return (await locator.innerText()).replace(/\s+/g, ' ').trim();
}

async function captureSellerFactGeometry(page: Page): Promise<Geometry> {
  const geometry = await page.getByTestId('seller-inbound-lines-table').evaluate((table) => {
    const doc = document.documentElement;
    const body = document.body;
    const container = table.closest('.MuiTableContainer-root') as HTMLElement | null;
    const headCells = Array.from(table.querySelectorAll('thead th')) as HTMLElement[];
    const rows = Array.from(
      table.querySelectorAll('tbody tr[data-testid="seller-inbound-line-row"]'),
    ) as HTMLElement[];
    const nameIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Наименование');
    const expectedIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Заявлено');
    const discrepancyIndex = headCells.findIndex((cell) => cell.textContent?.trim() === 'Расхождение');
    const containerRect = container?.getBoundingClientRect();
    const nameWidths = rows.map(
      (row) => (row.children[nameIndex] as HTMLElement | undefined)?.getBoundingClientRect().width ?? 0,
    );
    const rowHeights = rows.map((row) => row.getBoundingClientRect().height);
    const headerBottom = Math.max(...headCells.map((cell) => cell.getBoundingClientRect().bottom));
    const firstBodyTop = rows[0]?.getBoundingClientRect().top ?? 0;
    const firstNameRight =
      (rows[0]?.children[nameIndex] as HTMLElement | undefined)?.getBoundingClientRect().right ?? 0;
    const firstExpectedLeft =
      (rows[0]?.children[expectedIndex] as HTMLElement | undefined)?.getBoundingClientRect().left ?? 0;
    const buttonTexts = Array.from(document.querySelectorAll('button'))
      .filter((button) => {
        const rect = button.getBoundingClientRect();
        const style = window.getComputedStyle(button);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      })
      .map((button) => button.textContent?.replace(/\s+/g, ' ').trim() ?? '')
      .filter(Boolean);

    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      globalOverflowPx: Math.max(doc.scrollWidth, body.scrollWidth) - window.innerWidth,
      tableClientWidth: table.getBoundingClientRect().width,
      tableScrollWidth: table.scrollWidth,
      containerClientWidth: container?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      containerLeft: containerRect?.left ?? 0,
      containerRight: containerRect?.right ?? 0,
      headerCells: headCells.length,
      bodyCells: rows[0]?.children.length ?? 0,
      minNameWidth: Math.min(...nameWidths),
      maxRowHeight: Math.max(...rowHeights),
      headerBottom,
      firstBodyTop,
      firstNameRight,
      firstExpectedLeft,
      discrepancyHeaderLeft: headCells[discrepancyIndex]?.getBoundingClientRect().left ?? 0,
      discrepancyHeaderRight: headCells[discrepancyIndex]?.getBoundingClientRect().right ?? 0,
      visibleButtonTexts: buttonTexts,
    };
  });

  qaResult.geometry.sellerFactCard1280 = geometry;
  saveResult();
  return geometry;
}

function expectNoRawTechnicalText(text: string): void {
  for (const raw of [
    'collecting',
    'cancelled',
    'receiving',
    'sorting',
    'done',
    'mystery_state',
    'raw_mp',
    'undefined',
    'NaN',
    'null',
  ]) {
    expect(text).not.toContain(raw);
  }
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

test('F05 final current — FF conducts receiving and seller opens the same factual card', async ({
  page,
}) => {
  const suffix = `f05-final-${Date.now()}`;
  const seed = await seedFfSellerInbound(page, suffix);
  const requestId = await createSubmittedInbound(page, seed, {
    plannedBoxes: 2,
    expectedQty: 3,
  });
  const addedSku = `ff-added-f05-${suffix}`;
  const addedBarcode = `ff-added-f05-barcode-${suffix}`;
  qaResult.requestId = requestId;
  qaResult.expectedSku = seed.sku;
  qaResult.addedSku = addedSku;
  saveResult();

  await page.setViewportSize({ width: 1280, height: 900 });
  await loginFfAdmin(page, seed.adminEmail, seed.password);
  recordStep('FF logged in through the real login form');
  await page.getByTestId('nav-ff-reception').click();
  recordStep('FF opened reception queue');
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click();
  recordStep('FF opened the submitted inbound card');
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-compact-summary')).toContainText('Box Seller');
  await expect(page.getByTestId('ff-inbound-received-summary')).toContainText('0 из 3');

  await scanInboundSku(page, seed.sku);
  recordStep('FF scanned the planned SKU once');
  await scanInboundSku(page, seed.sku);
  recordStep('FF scanned the planned SKU twice, leaving shortage against expected 3');

  const ffShortageRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: seed.sku });
  await expect(ffShortageRow).toBeVisible();
  await expect(ffShortageRow.getByTestId('ff-inbound-line-expected')).toHaveText('3');
  await expect(ffShortageRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('2');
  await expect(ffShortageRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Недостача 1');

  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  recordStep('FF opened manual product creation from the receiving card');
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('F05 FF Added Product');
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
  recordStep('FF created and added an extra product to the factual receiving table');
  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);

  const ffAddedRow = page.getByTestId('ff-inbound-line-row-discrepancy').filter({ hasText: addedSku });
  await expect(ffAddedRow).toBeVisible();
  await expect(ffAddedRow.getByTestId('ff-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  await expect(ffAddedRow.getByTestId('ff-inbound-line-expected')).toHaveText('0');
  await expect(ffAddedRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
  await expect(ffAddedRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Излишек 1');
  await screenshot(page, '01-ff-card-before-complete-1280.png', true);

  await page.getByTestId('ff-inbound-verify-complete').click();
  recordStep('FF clicked complete receiving');
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: seed.sku })).toContainText(
    'Недостача 1',
  );
  await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: addedSku })).toContainText(
    'Излишек 1',
  );
  await screenshot(page, '02-ff-discrepancy-dialog-1280.png', true);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  ]);
  recordStep('FF confirmed discrepancy completion');
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');

  await page.route('**/api/operations/marketplace-unload-requests', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'mp-collecting-f05', status: 'collecting', line_count: 1, created_at: '2026-08-13T10:00:00Z' },
          { id: 'mp-cancelled-f05', status: 'cancelled', line_count: 1, created_at: '2026-08-12T10:00:00Z' },
        ]),
      });
      return;
    }
    await route.fallback();
  });

  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  recordStep('Seller logged in through the seller portal');
  await page.getByTestId('nav-seller-documents').click();
  recordStep('Seller opened documents');
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  const documentsText = await visibleText(page.getByTestId('seller-documents-table'));
  expect(documentsText).toContain('Поставка');
  expect(documentsText).toContain('В сортировке');
  expect(documentsText).toContain('На сборке');
  expect(documentsText).toContain('Отменено');
  expectNoRawTechnicalText(documentsText);
  qaResult.checks.documentsHumanStatuses = documentsText;
  saveResult();
  await screenshot(page, '03-seller-documents-human-statuses-1280.png', true);

  const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  await expect(sellerDocRow).toBeVisible();
  await sellerDocRow.click();
  recordStep('Seller opened the same conducted inbound card');

  await expect(page.getByRole('heading', { name: /Карточка приёмки.*Поставка/ })).toBeVisible();
  await expect(page.getByText('Новая заявка на поставку', { exact: true })).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);

  await expect(page.getByTestId('seller-inbound-summary-status')).toContainText('В сортировке');
  await expect(page.getByTestId('seller-inbound-summary-operation')).toContainText('Поставка');
  await expect(page.getByTestId('seller-inbound-summary-warehouse')).toContainText('WH');
  await expect(page.getByTestId('seller-inbound-summary-boxes')).toContainText('План 2');
  await expect(page.getByTestId('seller-inbound-summary-discrepancy')).toContainText('Есть');
  await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('Заявлено 3');
  await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('Факт 3');

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

  const factCardText = await visibleText(page.getByTestId('seller-inbound-fact-card'));
  expect(factCardText).toContain('Заявлено');
  expect(factCardText).toContain('Факт');
  expect(factCardText).toContain('Недостача 1');
  expect(factCardText).toContain('Излишек 1');
  expect(factCardText).toContain('Добавлено ФФ');
  expectNoRawTechnicalText(factCardText);
  qaResult.checks.sellerFactCardText = factCardText;
  saveResult();

  const geometry = await captureSellerFactGeometry(page);
  await screenshot(page, '04-seller-fact-card-1280.png', true);
  expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.containerScrollWidth).toBeLessThanOrEqual(geometry.containerClientWidth + 1);
  expect(geometry.discrepancyHeaderRight).toBeLessThanOrEqual(geometry.containerRight + 1);
  expect(geometry.headerCells).toBe(geometry.bodyCells);
  expect(geometry.minNameWidth).toBeGreaterThanOrEqual(240);
  expect(geometry.maxRowHeight).toBeLessThanOrEqual(120);
  expect(geometry.headerBottom).toBeLessThanOrEqual(geometry.firstBodyTop + 1);
  expect(geometry.firstNameRight).toBeLessThanOrEqual(geometry.firstExpectedLeft + 1);
  expect(geometry.visibleButtonTexts).not.toContain('Добавить товары');
  expect(geometry.visibleButtonTexts).not.toContain('Передать на склад');
  expect(geometry.visibleButtonTexts).not.toContain('Сохранить');
  expect(geometry.visibleButtonTexts).not.toContain('Удалить');
});
