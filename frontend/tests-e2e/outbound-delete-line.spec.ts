import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S10-001 — админ удаляет строку в draft отгрузке.
// TC-S09-004 — резерв освобождается при удалении строки draft.
test('удаление строки отгрузки в draft снимает резерв', async ({ page }) => {
  const email = `e2e-odl-${Date.now()}@example.com`;
  const sku = `SKU-ODL-${Date.now()}`;
  const whCode = `wh-odl-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E ODL');
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
  const whJson = (await wh.json()) as { id: string };
  const wid = whJson.id;

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

  const baseOut = '/api/operations/outbound-shipment-requests';
  await page.goto('/app/ops/outbound');
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await page.getByTestId('outbound-line-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('outbound-line-qty').fill('8');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'FROM-01' });
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-line').first()).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes('/api/operations/outbound-shipment-requests') &&
        r.url().includes('/lines/') &&
        r.status() === 200,
    ),
    page.getByTestId('outbound-line-delete').first().click(),
  ]);

  await expect(
    page.getByTestId('outbound-detail-lines').getByTestId('outbound-detail-line'),
  ).toHaveCount(0);

  await page.goto('/app/ops/transfers');
  await page.getByTestId('transfer-from-loc').selectOption({ label: 'FROM-01' });
  await page.getByTestId('transfer-to-loc').selectOption({ label: 'TO-01' });
  await page.getByTestId('transfer-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('transfer-qty').fill('3');
  const [trOk] = await Promise.all([
    waitForPostOk(page, '/api/operations/stock-transfers'),
    page.getByTestId('transfer-submit').click(),
  ]);
  expect(trOk.ok()).toBeTruthy();
});
