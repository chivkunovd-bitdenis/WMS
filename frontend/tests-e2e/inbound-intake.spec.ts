import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForLocationsListGet,
  waitForPostOk,
} from './api-waits';

test('create inbound request, add line, submit — UI and API', async ({ page }) => {
  const slug = `ff-inb-${Date.now()}`;
  const email = `e2e-inb-${Date.now()}@example.com`;
  const sku = `SKU-IN-${Date.now()}`;
  const whCode = `wh-${Date.now()}`;

  await page.goto('/');
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Inbound');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('operations-section')).toBeVisible();
  await expect(page.getByTestId('inbound-create-form')).toBeVisible();

  await page.getByTestId('warehouse-name').fill('Склад');
  await page.getByTestId('warehouse-code').fill(whCode);
  await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('warehouse-submit').click(),
  ]);

  await page.getByTestId('warehouse-list').getByTestId('warehouse-item').first().click();
  await expect(page.getByTestId('inbound-create-submit')).toBeEnabled();

  await page.getByTestId('location-code').fill('RCV-E2E');
  await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
    waitForLocationsListGet(page),
    page.getByTestId('location-submit').click(),
  ]);

  await page.getByTestId('product-name').fill('Товар');
  await page.getByTestId('product-sku').fill(sku);
  await page.getByTestId('product-length-mm').fill('50');
  await page.getByTestId('product-width-mm').fill('50');
  await page.getByTestId('product-height-mm').fill('50');
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);

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
