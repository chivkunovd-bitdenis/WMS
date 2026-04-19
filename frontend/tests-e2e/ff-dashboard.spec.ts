import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S15-003 — FF дашборд: недельный календарь и «Поставки и загрузки»; создание выгрузки на МП и открытие диалога состава.
// Given: админ ФФ, склад и товар в API; When: создаёт выгрузку и открывает строку; Then: диалог документа виден (negative: без склада — ошибка вместо успеха).
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

  const token = await page.evaluate(() => localStorage.getItem('wms_token'));
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
    }),
  });
  if (!prRes.ok()) {
    throw new Error(`product create failed: ${prRes.status()} ${await prRes.text()}`);
  }

  await page.reload();
  await expect(page.getByTestId('dashboard')).toBeVisible();

  await page.getByTestId('nav-ff-supplies-shipments').click();
  await expect(page.getByTestId('ff-supplies-shipments-page')).toBeVisible();
  await expect(page.getByTestId('ff-create-marketplace-download')).toBeVisible();
  await expect(page.getByTestId('ff-create-diverge')).toBeVisible();
  await page.getByTestId('ff-create-marketplace-download').click();
  await expect(page.getByTestId('ff-supplies-info-notice')).toBeVisible();

  await page.getByTestId('ff-docs-filter-mp-unload').click();
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

  await Promise.all([
    waitForPostOk(page, '/api/operations/marketplace-unload-requests', (u) => u.includes('/submit')),
    page.getByTestId('ff-supplies-doc-submit').click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Утверждено');
});
