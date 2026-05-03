import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S09-002 — второй исходящий не может зарезервировать сверх доступного (через блокировку перемещения).
// TC-S09-003 — перемещение ограничено доступным, когда исходящий резервирует остаток.
// TC-S08-005 — проведение отгрузки перевалидирует резервы и изменяет доступность.
test('резерв под отгрузку: перемещение блокируется, после проведения отгрузки — снова можно', async ({
  page,
}) => {
  const email = `e2e-or-${Date.now()}@example.com`;
  const sku = `SKU-OR-${Date.now()}`;
  const whCode = `wh-or-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E OR');
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
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/submit')),
    page.getByTestId('outbound-submit-request').click(),
  ]);

  await page.goto('/app/ops/transfers');
  await page.getByTestId('transfer-from-loc').selectOption({ label: 'FROM-01' });
  await page.getByTestId('transfer-to-loc').selectOption({ label: 'TO-01' });
  await page.getByTestId('transfer-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('transfer-qty').fill('3');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/api/operations/stock-transfers') &&
        r.status() === 422,
    ),
    page.getByTestId('transfer-submit').click(),
  ]);
  await expect(page.getByTestId('operations-error')).toContainText('insufficient_stock');

  await page.goto('/app/ops/outbound');
  await page
    .getByTestId('outbound-requests-list')
    .getByTestId('outbound-request-item')
    .first()
    .click();
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/post')),
    page.getByTestId('outbound-post-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('posted');

  await page.goto('/app/ops/transfers');
  await page.getByTestId('transfer-from-loc').selectOption({ label: 'FROM-01' });
  await page.getByTestId('transfer-to-loc').selectOption({ label: 'TO-01' });
  await page.getByTestId('transfer-product').selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('transfer-qty').fill('2');
  const [trOk] = await Promise.all([
    waitForPostOk(page, '/api/operations/stock-transfers'),
    page.getByTestId('transfer-submit').click(),
  ]);
  expect(trOk.ok()).toBeTruthy();
});
