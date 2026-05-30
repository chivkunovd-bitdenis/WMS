import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers';
import { setWmsDateField } from './wms-date-field-helpers';

// TC-S09-001 — селлер видит факт, зарезервировано и доступно на экране «Товары».
// TC-NEW-15-001 — без админской подсказки после приёмки: остаток в кабинете селлера.
test('seller products table shows on hand, reserved, and available after MP plan', async ({
  page,
}) => {
  test.setTimeout(120_000);
  const adminEmail = `e2e-sav-${Date.now()}@example.com`;
  const sellerEmail = `e2e-sav-sl-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const barcode = 'E2E-MOCK-BARCODE';
  const sku = `SKU-SAV-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller Avail');
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
    data: JSON.stringify({ name: 'WH', code: `wh-sav-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Avail Brand' }),
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

  await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  });

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Avail Product',
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

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'SAV-LOC' }),
  });
  const locId = String(((await locRes.json()) as { id: string }).id);

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
      storage_location_id: locId,
    }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const primIn = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  });
  const primInBody = (await primIn.json()) as {
    boxes: { id: string; internal_barcode: string }[];
  };
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    primInBody.boxes,
    barcode,
    [10],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  await expect
    .poll(async () => {
      const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, {
        headers: auth,
      });
      return ((await whs.json()) as unknown[]).length;
    })
    .toBeGreaterThan(0);

  await page.getByTestId('logout').click();
  await page.goto('/seller/');
  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await expect(page.getByTestId('app-frame')).toBeVisible();

  await Promise.all([
    waitForPostOk(page, '/api/operations/marketplace-unload-requests/seller'),
    page.getByTestId('seller-create-mp-unload').click(),
  ]);
  await expect(page.getByTestId('seller-mp-unload-dialog')).toBeVisible();
  await page.getByLabel('Склад WB (маркетплейс)').click();
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
  await page.getByTestId(`seller-mp-qty-${productId}`).locator('input').fill('4');
  await setWmsDateField(page, 'seller-mp-planned-date', '2026-06-15');
  await expect(page.getByTestId('seller-mp-plan')).toBeEnabled();
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PUT' &&
        r.url().includes('/lines') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/plan') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('seller-mp-plan').click(),
  ]);
  await page.getByTestId('seller-mp-close').click();

  await page.getByTestId('nav-seller-products').click();
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  const row = page.getByTestId('seller-product-row').filter({ hasText: sku });
  await expect(row).toBeVisible();
  await expect(row.getByTestId('seller-stock-on-hand')).toHaveText('10');
  await expect(row.getByTestId('seller-stock-reserved')).toHaveText('4');
  await expect(row.getByTestId('seller-stock-available')).toContainText('6');
  await expect(row.getByTestId('seller-stock-available-hint')).toContainText('(доступно 6)');
});
