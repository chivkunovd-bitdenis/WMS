import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';
import {beginInboundReceivingWithBoxes,  fulfillInboundViaBoxScans } from './inbound-boxes-helpers';
import { setWmsDateField } from './wms-date-field-helpers';

// TC-NEW-MP-04 — селлер создаёт отгрузку на МП, видит остаток и планирует.
// TC-NEW-MP-06 — после «Запланировать» документ в списке со статусом «Запланировано».
// TC-NEW-MP-020 — TASK-020 / DEC-015: plan-only UI, без коробов/упаковки/ship API.
// TC-NEW-MP-AVAIL-01 — товар только в «Сортировке» виден селлеру в подборе MP.
test('seller creates MP unload draft, plans with stock table', async ({ page }) => {
  test.setTimeout(120_000);
  const adminEmail = `e2e-smp-${Date.now()}@example.com`;
  const sellerEmail = `e2e-smp-sl-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const barcode = 'E2E-MOCK-BARCODE';
  const sku = `SKU-SMP-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller MP');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-smp-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'MP Brand' }),
  });
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  await page.request.patch(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: auth,
    data: JSON.stringify({
      content_api_token: 'e2e-content',
      supplies_api_token: 'e2e-supplies',
    }),
  });

  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: auth,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId }),
  });
  const jobId = String(((await jobRes.json()) as { id: string }).id);
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, {
        headers: auth,
      });
      return (await jr.json()) as { status: string };
    })
    .toMatchObject({ status: 'done' });

  const accRes = await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  });
  expect(accRes.ok()).toBeTruthy();

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'MP Sell Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);

  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
  });

  await page.request.patch(`${e2eApi}/products/${productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ packaging_instructions: 'E2E: пакет + стикер WB' }),
  });

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 10,
    }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  )
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    inboundBoxes,
    barcode,
    [10],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  const globalStock = await page.request.get(
    `${e2eApi}/operations/inventory-balances/summary`,
    { headers: auth, params: { warehouse_id: whId } },
  );
  const sortingOnly = (
    (await globalStock.json()) as {
      product_id: string;
      quantity_in_sorting: number;
      available: number;
    }[]
  ).find((row) => row.product_id === productId);
  expect(sortingOnly).toMatchObject({ quantity_in_sorting: 10, available: 0 });

  await expect
    .poll(async () => {
      const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, {
        headers: auth,
      });
      return ((await whs.json()) as unknown[]).length;
    })
    .toBeGreaterThan(0);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.goto('/seller/');
  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await expect(page.getByTestId('app-frame')).toBeVisible();

  await expect(page.getByTestId('seller-documents-table')).toBeVisible();

  await Promise.all([
    waitForPostOk(page, '/api/operations/marketplace-unload-requests/seller'),
    page.getByTestId('seller-create-mp-unload').click(),
  ]);
  await expect(page.getByTestId('seller-mp-unload-dialog')).toBeVisible();

  await page.getByLabel('Склад WB (маркетплейс)').click();
  await expect(page.getByRole('option', { name: /E2E WB склад/ })).toBeVisible();
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByRole('option', { name: /E2E WB склад/ }).click(),
  ]);
  await page
    .locator('[role="presentation"].MuiMenu-root')
    .first()
    .waitFor({ state: 'hidden', timeout: 5000 })
    .catch(() => undefined);
  const nullDatePatches: string[] = [];
  page.on('request', (req) => {
    if (req.method() !== 'PATCH' || !req.url().includes('/operations/marketplace-unload-requests/')) {
      return;
    }
    const body = req.postData() ?? '';
    if (body.includes('"planned_shipment_date":null')) {
      nullDatePatches.push(body);
    }
  });
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    setWmsDateField(page, 'seller-mp-planned-date', '2026-06-15'),
  ]);
  // TC-NEW-DATE-01 — дата не сбрасывается после blur (календарь → клик вне поля).
  const dateRoot = page.getByTestId('seller-mp-planned-date');
  await page.getByRole('dialog').getByRole('heading').first().click();
  await expect(dateRoot.getByRole('spinbutton', { name: 'Year' })).toHaveText('2026', {
    timeout: 5000,
  });
  await page.waitForTimeout(500);
  expect(nullDatePatches).toHaveLength(0);
  await page.getByTestId('seller-mp-add-products').click();
  await expect(page.getByTestId('seller-mp-picker')).toBeVisible();
  await page.getByTestId('seller-mp-picker-search').fill(sku);
  const sortingPickerRow = page.getByTestId('seller-mp-picker-row').filter({ hasText: sku });
  await expect(sortingPickerRow).toBeVisible();
  await expect(sortingPickerRow).toContainText('10');
  await page.getByTestId('seller-mp-picker-qty').first().fill('4');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.url().includes('/lines') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('seller-mp-picker-apply').click(),
  ]);
  await expect(page.getByTestId('seller-mp-picker')).toBeHidden();
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText(sku);
  await expect(page.getByTestId('seller-mp-plan')).toBeEnabled();

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.url().includes('/plan') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('seller-mp-plan').click(),
  ]);

  await expect(page.getByTestId('seller-mp-unload-dialog')).toContainText('Запланировано');
  // REV-FIX-012: hint that FF takes over after plan.
  await expect(page.getByTestId('seller-mp-ff-handoff-hint')).toContainText('фулфилмент');
  await expect(page.getByTestId('seller-mp-plan-only')).toBeVisible();
  await expect(page.getByTestId('ff-mp-box-add-products')).toHaveCount(0);
  await expect(page.getByTestId('ff-mp-packaging-complete')).toHaveCount(0);

  await page.getByTestId('seller-mp-close').click();
  const mpRow = page.locator('[data-doc-type="mp_unload"]').first();
  await expect(mpRow).toBeVisible();
  await expect(mpRow).toContainText('Запланировано');
});

// TC-NEW-MP-AVAILABLE-002 — поздние detail/availability заявки A не перезаписывают открытую заявку B.
test('seller MP dialog keeps request B after delayed request A resolves', async ({ page }) => {
  const suffix = Date.now();
  const adminEmail = `e2e-smp-race-${suffix}@example.com`;
  const sellerEmail = `e2e-smp-race-sl-${suffix}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller MP Race');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [registration] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const adminToken = String(
    ((await registration.json()) as { access_token: string }).access_token,
  );
  const adminHeaders = {
    Authorization: `Bearer ${adminToken}`,
    'Content-Type': 'application/json',
  };
  const warehouse = await page.request.post(`${e2eApi}/warehouses`, {
    headers: adminHeaders,
    data: JSON.stringify({ name: 'Race Warehouse', code: `race-${suffix}` }),
  });
  const warehouseId = String(((await warehouse.json()) as { id: string }).id);
  const seller = await page.request.post(`${e2eApi}/sellers`, {
    headers: adminHeaders,
    data: JSON.stringify({ name: 'Race Seller' }),
  });
  const sellerId = String(((await seller.json()) as { id: string }).id);
  const account = await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: adminHeaders,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  });
  expect(account.ok()).toBeTruthy();

  await page.getByTestId('logout').click();
  await page.goto('/seller/');
  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  const createRequestThroughUi = async () => {
    const [response] = await Promise.all([
      waitForPostOk(page, '/api/operations/marketplace-unload-requests/seller'),
      page.getByTestId('seller-create-mp-unload').click(),
    ]);
    const id = String(((await response.json()) as { id: string }).id);
    await expect(page.getByTestId('seller-mp-unload-dialog')).toBeVisible();
    await page.getByTestId('seller-mp-close').click();
    await expect(page.getByTestId('seller-mp-unload-dialog')).toBeHidden();
    return id;
  };
  const requestA = await createRequestThroughUi();
  const requestB = await createRequestThroughUi();

  const productId = '11111111-1111-4111-8111-111111111111';
  const detail = (id: string, warehouseName: string, status: string, productName: string) => ({
    id,
    warehouse_id: warehouseId,
    warehouse_name: warehouseName,
    status,
    wb_mp_warehouse_id: null,
    planned_shipment_date: null,
    lines: [
      {
        id: `${id.slice(0, 8)}-2222-4222-8222-222222222222`,
        product_id: productId,
        sku_code: productName,
        product_name: productName,
        quantity: 1,
      },
    ],
  });
  let releaseA!: () => void;
  const holdA = new Promise<void>((resolve) => {
    releaseA = resolve;
  });
  let resolveAStarted!: () => void;
  const aStarted = new Promise<void>((resolve) => {
    resolveAStarted = resolve;
  });
  let resolveAFinished!: () => void;
  const aFinished = new Promise<void>((resolve) => {
    resolveAFinished = resolve;
  });
  let aStartedCount = 0;
  let aFinishedCount = 0;
  const racePattern = '**/operations/marketplace-unload-requests/**';
  await page.route(racePattern, async (route) => {
    const url = new URL(route.request().url());
    const isAvailability = url.pathname.endsWith('/available-products');
    const excludedRequest = url.searchParams.get('exclude_request_id');
    const isDetailA = url.pathname.endsWith(`/${requestA}`);
    const isDetailB = url.pathname.endsWith(`/${requestB}`);
    const isAvailabilityA = isAvailability && excludedRequest === requestA;
    const isAvailabilityB = isAvailability && excludedRequest === requestB;
    if (isDetailA || isAvailabilityA) {
      aStartedCount += 1;
      if (aStartedCount === 2) resolveAStarted();
      await holdA;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          isDetailA
            ? detail(requestA, 'STALE WAREHOUSE A', 'submitted', 'STALE-SKU-A')
            : [
                {
                  product_id: productId,
                  sku_code: 'STALE-SKU-A',
                  product_name: 'STALE-SKU-A',
                  available: 1,
                },
              ],
        ),
      });
      aFinishedCount += 1;
      if (aFinishedCount === 2) resolveAFinished();
      return;
    }
    if (isDetailB || isAvailabilityB) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          isDetailB
            ? detail(requestB, 'CURRENT WAREHOUSE B', 'draft', 'CURRENT-SKU-B')
            : [
                {
                  product_id: productId,
                  sku_code: 'CURRENT-SKU-B',
                  product_name: 'CURRENT-SKU-B',
                  available: 9,
                },
              ],
        ),
      });
      return;
    }
    await route.continue();
  });

  await page
    .locator(`[data-testid="seller-documents-row"][data-doc-id="${requestA}"]`)
    .click();
  await aStarted;
  await page.getByTestId('seller-mp-close').click();
  await page
    .locator(`[data-testid="seller-documents-row"][data-doc-id="${requestB}"]`)
    .click();
  await expect(page.getByTestId('seller-mp-unload-dialog')).toContainText(
    'CURRENT WAREHOUSE B · Черновик',
  );
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText('CURRENT-SKU-B');
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText('9');
  await expect(page.getByTestId('seller-mp-add-products')).toBeEnabled();

  releaseA();
  await aFinished;
  await expect(page.getByTestId('seller-mp-unload-dialog')).toContainText(
    'CURRENT WAREHOUSE B · Черновик',
  );
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText('CURRENT-SKU-B');
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText('9');
  await expect(page.getByTestId('seller-mp-unload-dialog')).not.toContainText(
    'STALE WAREHOUSE A',
  );
  await expect(page.getByTestId('seller-mp-add-products')).toBeEnabled();
  await page.unroute(racePattern);
});
