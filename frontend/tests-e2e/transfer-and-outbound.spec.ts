import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPatchOk,
  waitForPostOk,
  waitForOutboundShipOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { setInboundPlannedBoxes } from './inbound-boxes-helpers';

// TC-S07-001, TC-S08-001 — перемещение остатка и отгрузка (UI).
test('stock transfer and outbound shipment — UI', async ({ page }) => {
  const email = `e2e-tro-${Date.now()}@example.com`;
  const sku = `SKU-TRO-${Date.now()}`;
  const whCode = `wh-tro-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E TRO');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const token = regJson.access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  expect(wh.ok()).toBeTruthy();
  const wid = String(((await wh.json()) as { id: string }).id);
  const locFrom = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'FROM-01' },
  });
  expect(locFrom.ok()).toBeTruthy();
  const locTo = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'TO-01' },
  });
  expect(locTo.ok()).toBeTruthy();
  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  expect(pr.ok()).toBeTruthy();

  const baseIn = '/api/operations/inbound-intake-requests';
  await page.goto('/app/ops/inbound');
  const [createRes] = await Promise.all([
    waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('inbound-create-submit').click(),
  ]);
  const inboundId = String(((await createRes.json()) as { id: string }).id);
  await setInboundPlannedBoxes(page.request, h, inboundId, 1);
  await page.getByTestId('inbound-line-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('inbound-line-qty').fill('10');
  await page.getByTestId('inbound-line-location').selectOption({ label: 'FROM-01' });
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/lines')),
    page.getByTestId('inbound-line-submit').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/submit')),
    page.getByTestId('inbound-submit-request').click(),
  ]);
  await Promise.all([
    waitForPatchOk(page, baseIn, (u) => u.includes('/actual')),
    waitForPostOk(page, baseIn, (u) => u.includes('/boxes')),
    page.getByTestId('inbound-primary-accept').click(),
  ]);
  await expect(page.getByTestId('inbound-detail-status')).toContainText('receiving');
  const { v2InboundBoxIntakeUi } = await import('./inbound-boxes-helpers');
  await v2InboundBoxIntakeUi(page, h, sku, 10);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/verify')),
    page.getByTestId('inbound-verify-complete').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/post')),
    page.getByTestId('inbound-post-submit').click(),
  ]);

  await page.goto('/app/ops/movements');
  await expect(page.getByTestId('global-movements-section')).toBeVisible();
  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-movements'),
    page.getByTestId('global-movements-refresh').click(),
  ]);
  await expect(
    page.getByTestId('global-movements-list').getByTestId('global-movement-row').first(),
  ).toContainText(sku);

  await page.goto('/app/ops/transfers');
  await page.getByTestId('transfer-from-loc').selectOption({ label: 'FROM-01' });
  await page.getByTestId('transfer-to-loc').selectOption({ label: 'TO-01' });
  await page.getByTestId('transfer-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('transfer-qty').fill('3');
  await expect(page.getByTestId('transfer-summary')).toContainText('FROM-01 → TO-01');
  const [trRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/stock-transfers'),
    page.getByTestId('transfer-submit').click(),
  ]);
  expect(trRes.ok()).toBeTruthy();
  await expect(page.getByTestId('transfer-operation-row')).toContainText('FROM-01 → TO-01');

  await page.goto('/app/ops/movements');
  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-movements'),
    page.getByTestId('global-movements-refresh').click(),
  ]);
  await expect(page.getByTestId('global-movements-list')).toContainText('Перемещение: списано');

  const baseOut = '/api/operations/outbound-shipment-requests';
  await page.goto('/app/ops/outbound');
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('draft');
  await page.getByTestId('outbound-line-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('outbound-line-qty').fill('3');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'TO-01' });
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/submit')),
    page.getByTestId('outbound-submit-request').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('submitted');
  await page.getByTestId('outbound-line-ship-qty').fill('1');
  await Promise.all([
    waitForOutboundShipOk(page),
    page.getByTestId('outbound-line-ship-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('submitted');
  await expect(
    page.getByTestId('outbound-detail-lines').getByTestId('outbound-detail-line').first(),
  ).toContainText('1 из 3');
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/post')),
    page.getByTestId('outbound-post-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('posted');
  const movRows = page
    .getByTestId('outbound-movements-list')
    .getByTestId('outbound-movement-row');
  await expect(movRows).toHaveCount(2);
  await expect(movRows.nth(0)).toContainText('Отгрузка');
  await expect(movRows.nth(1)).toContainText('Отгрузка');
});

// TC-NEW-WAREHOUSE-TRANSFER-CONTEXT — выбранный склад фильтрует обычные transfer-группы,
// а межскладская пара остаётся одной строкой и раскрывает обе стороны без UUID в интерфейсе.
test('warehouse context filters transfers and shows the matching side of a cross-warehouse pair', async ({ page }) => {
  const email = `e2e-transfer-context-${Date.now()}@example.com`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Transfer Context');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  const northId = '10000000-0000-4000-8000-000000000001';
  const southId = '10000000-0000-4000-8000-000000000002';
  const crossGroupId = '20000000-0000-4000-8000-000000000001';
  const localGroupId = '20000000-0000-4000-8000-000000000002';
  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: northId, name: 'Склад Север', code: 'NORTH', is_operational: true, is_primary: true },
        { id: southId, name: 'Склад Юг', code: 'SOUTH', is_operational: true, is_primary: false },
      ]),
    });
  });
  await page.route('**/api/warehouses/*/locations', async (route) => {
    const isNorth = route.request().url().includes(northId);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(isNorth
        ? [
            { id: 'north-from', code: 'N-01', warehouse_id: northId, barcode: 'N-01' },
            { id: 'north-to', code: 'N-02', warehouse_id: northId, barcode: 'N-02' },
          ]
        : [{ id: 'south-to', code: 'S-01', warehouse_id: southId, barcode: 'S-01' }]),
    });
  });
  await page.route('**/api/operations/inventory-movements?limit=80', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'movement-cross-out', product_id: 'product-1', sku_code: 'SKU-CROSS', product_name: 'Кросс-товар',
          storage_location_id: 'north-from', storage_location_code: 'N-01', warehouse_id: northId,
          warehouse_name: 'Склад Север', quantity_delta: -3, movement_type: 'stock_transfer_out',
          transfer_group_id: crossGroupId, created_at: '2026-08-22T06:00:00Z',
        },
        {
          id: 'movement-cross-in', product_id: 'product-1', sku_code: 'SKU-CROSS', product_name: 'Кросс-товар',
          storage_location_id: 'south-to', storage_location_code: 'S-01', warehouse_id: southId,
          warehouse_name: 'Склад Юг', quantity_delta: 3, movement_type: 'stock_transfer_in',
          transfer_group_id: crossGroupId, created_at: '2026-08-22T06:00:00Z',
        },
        {
          id: 'movement-local-out', product_id: 'product-2', sku_code: 'SKU-LOCAL', product_name: 'Обычный товар',
          storage_location_id: 'north-from', storage_location_code: 'N-01', warehouse_id: northId,
          warehouse_name: 'Склад Север', quantity_delta: -2, movement_type: 'stock_transfer_out',
          transfer_group_id: localGroupId, created_at: '2026-08-22T05:00:00Z',
        },
        {
          id: 'movement-local-in', product_id: 'product-2', sku_code: 'SKU-LOCAL', product_name: 'Обычный товар',
          storage_location_id: 'north-to', storage_location_code: 'N-02', warehouse_id: northId,
          warehouse_name: 'Склад Север', quantity_delta: 2, movement_type: 'stock_transfer_in',
          transfer_group_id: localGroupId, created_at: '2026-08-22T05:00:00Z',
        },
      ]),
    });
  });

  await page.reload();
  await page.goto('/app/ops/transfers');

  const list = page.getByTestId('transfer-operations-list');
  await expect(page.getByTestId('transfers-warehouse-context')).toContainText('Склад Север');
  await expect(list.getByText('SKU-CROSS — Кросс-товар')).toBeVisible();
  await expect(list.getByText('SKU-LOCAL — Обычный товар')).toBeVisible();
  await expect(list.getByText('Из склада «Склад Север»')).toBeVisible();

  await page.getByTestId(`transfer-operation-toggle-${crossGroupId}`).click();
  const details = page.getByTestId(`transfer-operation-details-${crossGroupId}`);
  await expect(details).toContainText('Из склада «Склад Север» · ячейка N-01');
  await expect(details).toContainText('В склад «Склад Юг» · ячейка S-01');
  await expect(list.getByText(crossGroupId)).toHaveCount(0);

  await page.getByTestId('transfers-warehouse-context-button').click();
  await page.getByTestId(`transfers-warehouse-context-option-${southId}`).click();
  await expect(list.getByText('В склад «Склад Юг»')).toBeVisible();
  await expect(list.getByText('SKU-CROSS — Кросс-товар')).toBeVisible();
  await expect(list.getByText('SKU-LOCAL — Обычный товар')).toHaveCount(0);
});
