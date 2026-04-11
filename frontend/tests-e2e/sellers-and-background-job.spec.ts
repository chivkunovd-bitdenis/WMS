import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';

/**
 * Реальный путь: экраны каталога и операций, кнопки, фоновая задача до статуса done.
 */
test('create seller, product with seller, run movements digest job', async ({ page }) => {
  const slug = `ff-sbj-${Date.now()}`;
  const email = `e2e-sbj-${Date.now()}@example.com`;
  const sku = `SKU-SBJ-${Date.now()}`;
  const whCode = `wh-sbj-${Date.now()}`;

  await page.goto('/');
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E SB');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('sellers-section')).toBeVisible();
  await page.getByTestId('seller-name').fill('ACME Seller');
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForGetOk(page, '/api/sellers'),
    page.getByTestId('seller-submit').click(),
  ]);
  await expect(page.getByTestId('seller-list').getByTestId('seller-item').first()).toContainText(
    'ACME Seller',
  );

  await page.getByTestId('warehouse-name').fill('WH');
  await page.getByTestId('warehouse-code').fill(whCode);
  await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('warehouse-submit').click(),
  ]);
  await page.getByTestId('warehouse-list').getByTestId('warehouse-item').first().click();

  await page.getByTestId('product-name').fill('Item');
  await page.getByTestId('product-sku').fill(sku);
  await page.getByTestId('product-length-mm').fill('10');
  await page.getByTestId('product-width-mm').fill('10');
  await page.getByTestId('product-height-mm').fill('10');
  await page.getByTestId('product-seller').selectOption({ label: 'ACME Seller' });
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);

  const prodRow = page.getByTestId('product-list').getByTestId('product-item').filter({ hasText: sku });
  await expect(prodRow).toBeVisible();
  await expect(prodRow.getByTestId('product-seller-name')).toContainText('ACME Seller');

  await expect(page.getByTestId('background-job-section')).toBeVisible();
  const jobPost = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/api/operations/background-jobs') &&
      r.status() === 202,
  );
  await Promise.all([jobPost, page.getByTestId('background-job-start').click()]);
  await expect(page.getByTestId('background-job-status')).toContainText('done', { timeout: 25_000 });
  await expect(page.getByTestId('background-job-result')).toContainText('Всего движений');
});
