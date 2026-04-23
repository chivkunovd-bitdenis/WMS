import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
  waitForOutboundShipOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

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
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('inbound-create-submit').click(),
  ]);
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
    waitForPostOk(page, baseIn, (u) => u.includes('/primary-accept')),
    page.getByTestId('inbound-primary-accept').click(),
  ]);
  await page.getByTestId('inbound-line-actual-qty').fill('10');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/api/operations/inbound-intake-requests') &&
        r.url().includes('/actual') &&
        r.status() === 200,
    ),
    page.getByTestId('inbound-line-actual-save').click(),
  ]);
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
  const [trRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/stock-transfers'),
    page.getByTestId('transfer-submit').click(),
  ]);
  expect(trRes.ok()).toBeTruthy();

  await page.goto('/app/ops/movements');
  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-movements'),
    page.getByTestId('global-movements-refresh').click(),
  ]);
  await expect(page.getByTestId('global-movements-list')).toContainText('stock_transfer_out');

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
  await expect(movRows.nth(0)).toContainText('outbound_shipment');
  await expect(movRows.nth(1)).toContainText('outbound_shipment');
});
