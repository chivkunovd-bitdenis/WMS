import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { setWmsDateField } from './wms-date-field-helpers';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S15-003 — FF дашборд: недельный календарь; отгрузка ФФ→МП из раздела «Отгрузки на МП».
// Given: админ ФФ, склад и товар в API; When: создаёт отгрузку на МП и открывает строку; Then: диалог документа виден (negative: без склада — ошибка вместо успеха).
test('fulfillment admin sees week calendar and supplies-shipments page', async ({ page }) => {
  const email = `e2e-ff-dash-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Dashboard');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('ff-week-calendar')).toBeVisible();
  await expect(page.getByTestId('ff-dashboard-inbound-block')).toBeVisible();
  await expect(page.getByTestId('ff-dashboard-outbound-block')).toBeVisible();

  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'));
  expect(token).toBeTruthy();
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: JSON.stringify({
      name: 'E2E FF Dash',
      code: `e2e-ff-${Date.now()}`,
    }),
  });
  if (!whRes.ok()) {
    throw new Error(`warehouse create failed: ${whRes.status()} ${await whRes.text()}`);
  }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: JSON.stringify({ name: 'E2E FF seller' }),
  });
  if (!sellerRes.ok()) {
    throw new Error(`seller create failed: ${sellerRes.status()} ${await sellerRes.text()}`);
  }
  const sellerId = (await sellerRes.json()) as { id: string };
  const tokRes = await page.request.patch(
    `${e2eApi}/integrations/wildberries/sellers/${sellerId.id}/tokens`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: JSON.stringify({
        content_api_token: 'e2e-content',
        supplies_api_token: 'e2e-ff-supplies-token',
      }),
    },
  );
  if (!tokRes.ok()) {
    throw new Error(`wb supplies token patch failed: ${tokRes.status()} ${await tokRes.text()}`);
  }
  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId.id }),
  });
  const jobId = String(((await jobRes.json()) as { id: string }).id);
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return (await jr.json()) as { status: string };
    })
    .toMatchObject({ status: 'done' });

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: JSON.stringify({
      name: 'E2E FF product',
      sku_code: `e2e-ff-sku-${Date.now()}`,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerId.id,
    }),
  });
  if (!prRes.ok()) {
    throw new Error(`product create failed: ${prRes.status()} ${await prRes.text()}`);
  }
  const productJson = (await prRes.json()) as { id: string; sku_code: string };
  const productId = String(productJson.id);
  const barcode = 'E2E-MOCK-BARCODE';
  await page.request.post(
    `${e2eApi}/integrations/wildberries/sellers/${sellerId.id}/link-product`,
    {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
    },
  );
  const whId = String(((await whRes.json()) as { id: string }).id);
  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: JSON.stringify({ code: 'MP-PICK' }),
  });
  if (!locRes.ok()) {
    throw new Error(`location create failed: ${locRes.status()} ${await locRes.text()}`);
  }
  const locId = String(((await locRes.json()) as { id: string }).id);
  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: JSON.stringify({ warehouse_id: whId }),
  });
  if (!inbound.ok()) {
    throw new Error(`inbound create failed: ${inbound.status()} ${await inbound.text()}`);
  }
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  const inboundLine = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: JSON.stringify({ product_id: productId, expected_qty: 5, storage_location_id: locId }),
  });
  if (!inboundLine.ok()) {
    throw new Error(`inbound line failed: ${inboundLine.status()} ${await inboundLine.text()}`);
  }
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: { Authorization: `Bearer ${token}` } });
  const primRes = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: { actual_box_count: 1 },
  });
  const primBody = (await primRes.json()) as {
    boxes: { id: string; internal_barcode: string }[];
  };
  const { fulfillInboundViaBoxScans } = await import('./inbound-boxes-helpers');
  await fulfillInboundViaBoxScans(
    page.request,
    { Authorization: `Bearer ${token}` },
    inboundId,
    primBody.boxes,
    barcode,
    [5],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: { Authorization: `Bearer ${token}` } });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: { Authorization: `Bearer ${token}` } });

  await page.reload();
  await expect(page.getByTestId('dashboard')).toBeVisible();

  await page.getByTestId('nav-ff-mp-shipments').click();
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible();
  await expect(page.getByTestId('ff-create-mp-shipment')).toBeVisible();
  await page.getByTestId('ff-create-mp-shipment').click();
  await expect(page.getByTestId('ff-supplies-info-notice')).toBeVisible();
  // Creating a document opens it immediately; close before interacting with the list.
  if (await page.getByTestId('ff-supplies-doc-dialog').isVisible().catch(() => false)) {
    await page.getByTestId('ff-supplies-doc-close').click();
    await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeHidden();
  }
  await Promise.all([
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible();

  await page.getByTestId('ff-supplies-line-product').click();
  await page.getByRole('option', { name: /E2E FF product/ }).click();
  await Promise.all([
    waitForPostOk(
      page,
      '/api/operations/marketplace-unload-requests',
      (u) => u.includes('/lines') && !u.includes('/submit'),
    ),
    page.getByTestId('ff-supplies-line-add').click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-lines')).toContainText('E2E FF product');

  await page.getByLabel('Склад WB (маркетплейс)').click();
  await page.getByRole('option', { name: /E2E WB склад/ }).click();
  await setWmsDateField(page, 'ff-mp-planned-date', '2026-06-15');
  await page.waitForResponse(
    (r) =>
      r.request().method() === 'PATCH' &&
      r.url().includes('/operations/marketplace-unload-requests/') &&
      r.status() >= 200 &&
      r.status() < 300,
  );
  await Promise.all([
    waitForPostOk(page, '/api/operations/marketplace-unload-requests', (u) => u.includes('/confirm')),
    page.getByTestId('ff-supplies-doc-submit').click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Утверждено');
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible();
});
