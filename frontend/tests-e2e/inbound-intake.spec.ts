import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForLocationsListGet,
  waitForPostOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S06-001, TC-S06-002, TC-S06-004 — черновик приёмки, строка, submit (UI + API).
test('create inbound request, add line, submit — UI and API', async ({ page }) => {
  const email = `e2e-inb-${Date.now()}@example.com`;
  const sku = `SKU-IN-${Date.now()}`;
  const whCode = `wh-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Inbound');
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

  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'RCV-E2E' },
  });
  expect(loc.ok()).toBeTruthy();

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 50, width_mm: 50, height_mm: 50 },
  });
  expect(pr.ok()).toBeTruthy();

  await page.goto('/app/ops/inbound');
  await expect(page.getByTestId('inbound-create-form')).toBeVisible();
  await expect(page.getByTestId('inbound-create-submit')).toBeEnabled();

  const [createRes] = await Promise.all([
    waitForPostOk(
      page,
      '/api/operations/inbound-intake-requests',
      (u) => !u.includes('/lines') && !u.includes('/submit'),
    ),
    page.getByTestId('inbound-create-submit').click(),
  ]);
  expect(createRes.ok()).toBeTruthy();
  await expect(page.getByTestId('operations-error')).toHaveCount(0);
  await expect(page.getByTestId('inbound-detail-status')).toContainText('draft');
  await expect(page.getByTestId('inbound-detail-planned-date')).toBeVisible();

  await page
    .getByTestId('inbound-line-product')
    .selectOption({ label: `${sku} — Товар` });
  await page.getByTestId('inbound-line-qty').fill('4');
  await page
    .getByTestId('inbound-line-location')
    .selectOption({ label: 'RCV-E2E' });

  const [lineRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/lines'),
    ),
    page.getByTestId('inbound-line-submit').click(),
  ]);
  expect(lineRes.ok()).toBeTruthy();
  await expect(page.getByTestId('inbound-detail-line')).toContainText(sku);
  await expect(page.getByTestId('inbound-detail-line')).toContainText('4');

  const [submitRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/submit'),
    ),
    page.getByTestId('inbound-submit-request').click(),
  ]);
  expect(submitRes.ok()).toBeTruthy();
  await expect(page.getByTestId('inbound-detail-status')).toContainText('submitted');
  await expect(
    page.getByTestId('inbound-requests-list').getByTestId('inbound-request-item').first(),
  ).toContainText('submitted');

  const [primRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/primary-accept'),
    ),
    page.getByTestId('inbound-primary-accept').click(),
  ]);
  expect(primRes.ok()).toBeTruthy();
  await expect(page.getByTestId('inbound-detail-status')).toContainText('primary_accepted');

  await page.getByTestId('inbound-line-actual-qty').fill('4');
  const [actualRes] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/api/operations/inbound-intake-requests') &&
        r.url().includes('/actual') &&
        r.status() === 200,
    ),
    page.getByTestId('inbound-line-actual-save').click(),
  ]);
  expect(actualRes.ok()).toBeTruthy();

  const [verifyRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/verify'),
    ),
    page.getByTestId('inbound-verify-complete').click(),
  ]);
  expect(verifyRes.ok()).toBeTruthy();
  await expect(page.getByTestId('inbound-detail-status')).toContainText('verified');

  const [postRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) =>
      u.includes('/post'),
    ),
    page.getByTestId('inbound-post-submit').click(),
  ]);
  expect(postRes.ok()).toBeTruthy();
  await expect(page.getByTestId('inbound-detail-status')).toContainText('posted');
  await expect(
    page.getByTestId('inbound-movements-list').getByTestId('inbound-movement-row').first(),
  ).toContainText('+4');
  const invRow = page
    .getByTestId('inventory-balance-list')
    .getByTestId('inventory-balance-row')
    .first();
  await expect(invRow).toContainText(sku);
  await expect(invRow).toContainText('4');
});
