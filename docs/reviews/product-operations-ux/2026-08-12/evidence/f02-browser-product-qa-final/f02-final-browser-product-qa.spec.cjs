const fs = require('node:fs');
const path = require('node:path');

const { expect, test } = require('../../../../../../frontend/node_modules/@playwright/test');
const { waitForPatchOk } = require('../../../../../../frontend/tests-e2e/api-waits');
const {
  apiCreateSubmittedInbound,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} = require('../../../../../../frontend/tests-e2e/inbound-boxes-helpers');

const evidenceDir = __dirname;
const screenshotsDir = path.join(evidenceDir, 'screenshots');

async function captureUiMetrics(page, name) {
  const metrics = await page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const rootStyle = getComputedStyle(root);
    const bodyStyle = getComputedStyle(body);

    return {
      name: document.title,
      viewportWidth,
      viewportHeight,
      documentScrollWidth: root.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      documentClientWidth: root.clientWidth,
      bodyClientWidth: body.clientWidth,
      horizontalOverflowPx: Math.max(root.scrollWidth, body.scrollWidth) - viewportWidth,
      rootBackground: rootStyle.backgroundColor,
      bodyBackground: bodyStyle.backgroundColor,
      blackViewportBackground:
        rootStyle.backgroundColor === 'rgb(0, 0, 0)' || bodyStyle.backgroundColor === 'rgb(0, 0, 0)',
    };
  });

  fs.writeFileSync(path.join(evidenceDir, `${name}-ui-metrics.json`), `${JSON.stringify(metrics, null, 2)}\n`);
  return metrics;
}

test.describe.configure({ timeout: 120_000 });

test('F02 final browser product QA at 1280px', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  fs.mkdirSync(screenshotsDir, { recursive: true });

  const stepsClicked = [];
  const seed = await seedFfSellerInbound(page, `f02-final-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 1, expectedQty: 1 });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await openFfInboundDoc(page, seed, { skipLogin: true });
  stepsClicked.push('open FF reception card from queue');

  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root').getByRole('heading', { name: 'Приёмка' })).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Поставка');
  await expect(page.getByTestId('ff-inbound-return-autoprint')).toHaveCount(0);

  const productRow = page
    .getByTestId('ff-inbound-lines-table')
    .locator('tbody tr')
    .filter({ hasText: seed.sku });
  await expect(productRow).toBeVisible();

  const beforeMetrics = await captureUiMetrics(page, '01-before');
  expect(beforeMetrics.horizontalOverflowPx).toBeLessThanOrEqual(0);
  expect(beforeMetrics.blackViewportBackground).toBe(false);
  await page.screenshot({
    path: path.join(screenshotsDir, '01-1280-inbound-row-before-dimensions.png'),
    fullPage: true,
  });

  const dimensionsButtonInfo = await productRow
    .getByTestId('ff-inbound-line-dimensions-edit')
    .evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        ariaLabel: el.getAttribute('aria-label'),
        text: el.textContent?.trim() ?? '',
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    });
  expect(dimensionsButtonInfo.ariaLabel).toBe('Габариты');
  expect(dimensionsButtonInfo.width).toBeLessThanOrEqual(40);
  expect(dimensionsButtonInfo.height).toBeLessThanOrEqual(40);

  await productRow.getByTestId('ff-inbound-line-dimensions-edit').click();
  stepsClicked.push('click compact dimensions icon in product row');
  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toBeVisible();
  await page.waitForTimeout(350);
  const dialogMetrics = await captureUiMetrics(page, '02-dialog-open');
  expect(dialogMetrics.horizontalOverflowPx).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: path.join(screenshotsDir, '02-1280-dimensions-dialog-open.png'),
    fullPage: true,
  });

  await page.getByTestId('ff-inbound-dimensions-length').fill('200');
  await page.getByTestId('ff-inbound-dimensions-width').fill('100');
  await page.getByTestId('ff-inbound-dimensions-height').fill('50');
  stepsClicked.push('fill dimensions 200x100x50');
  await page.screenshot({
    path: path.join(screenshotsDir, '03-1280-dimensions-dialog-filled.png'),
    fullPage: true,
  });

  await Promise.all([
    waitForPatchOk(page, '/api/products', (u) => u.includes('/dimensions')),
    page.getByTestId('ff-inbound-dimensions-save').click(),
  ]);
  stepsClicked.push('save dimensions');

  await expect(page.getByTestId('ff-inbound-dimensions-dialog')).toHaveCount(0);
  await expect(productRow.getByTestId('ff-inbound-line-dimensions')).toContainText('200×100×50 мм');
  await expect(productRow.getByTestId('ff-inbound-line-dimensions')).toContainText('1.00 л');

  const afterMetrics = await captureUiMetrics(page, '04-after-save');
  expect(afterMetrics.horizontalOverflowPx).toBeLessThanOrEqual(0);
  expect(afterMetrics.blackViewportBackground).toBe(false);
  await page.screenshot({
    path: path.join(screenshotsDir, '04-1280-saved-dimensions-visible.png'),
    fullPage: true,
  });

  const productReadbackResponse = await page.request.get('/api/products', {
    headers: { Authorization: `Bearer ${seed.token}` },
  });
  expect(productReadbackResponse.ok()).toBe(true);
  const productsReadback = await productReadbackResponse.json();
  const productReadback = productsReadback.find((product) => product.id === seed.productId || product.sku_code === seed.sku);
  expect(productReadback).toBeTruthy();
  expect(productReadback.length_mm).toBe(200);
  expect(productReadback.width_mm).toBe(100);
  expect(productReadback.height_mm).toBe(50);
  expect(Number(productReadback.volume_liters)).toBe(1);

  const visibleText = await page.getByTestId('ff-inbound-doc-root').innerText();
  const result = {
    status: 'BROWSER_PRODUCT_QA_PASSED',
    runDate: '2026-08-13',
    url: page.url(),
    viewport: { width: 1280, height: 800 },
    seedSku: seed.sku,
    operationTypeText: await page.getByTestId('ff-inbound-operation-type').innerText(),
    rowDimensionsText: await productRow.getByTestId('ff-inbound-line-dimensions').innerText(),
    returnAutoprintControlCount: await page.getByTestId('ff-inbound-return-autoprint').count(),
    visibleReturnAutoprintText: visibleText.includes('Печатать ШК при скане'),
    dimensionsButtonInfo,
    backendReadback: {
      length_mm: productReadback.length_mm,
      width_mm: productReadback.width_mm,
      height_mm: productReadback.height_mm,
      volume_liters: productReadback.volume_liters,
    },
    uiMetrics: {
      beforeMetrics,
      dialogMetrics,
      afterMetrics,
    },
    stepsClicked,
    screenshots: [
      'screenshots/01-1280-inbound-row-before-dimensions.png',
      'screenshots/02-1280-dimensions-dialog-open.png',
      'screenshots/03-1280-dimensions-dialog-filled.png',
      'screenshots/04-1280-saved-dimensions-visible.png',
    ],
  };

  fs.writeFileSync(path.join(evidenceDir, 'f02-final-browser-product-qa-result.json'), `${JSON.stringify(result, null, 2)}\n`);
});
