import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForLocationsListGet, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S03-001 — админ создаёт склад.
// TC-S03-002 — админ создаёт ячейку (локацию) в складе.
// TC-S05-001 — админ создаёт товар с обязательными полями.
test('register then create warehouse, location, and product', async ({ page }) => {
  const email = `e2e-cat-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
  await expect(page.getByTestId('warehouse-form')).toHaveCount(0);
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Catalog FF');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await page.goto('/app/catalog');
  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('warehouse-form')).toBeVisible();
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);

  await page.getByTestId('warehouse-name').fill('Основной');
  await page.getByTestId('warehouse-code').fill('main-wh');

  const [whPost, whListAfterCreate] = await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('warehouse-submit').click(),
  ]);
  expect(whPost.ok()).toBeTruthy();
  expect(whListAfterCreate.ok()).toBeTruthy();
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);

  await expect(page.getByTestId('warehouse-list').getByTestId('warehouse-item')).toContainText('main-wh');
  await expect(page.getByTestId('warehouse-list').getByTestId('warehouse-item')).toContainText('Основной');
  await expect(page.getByTestId('location-form')).toBeVisible();

  await page.getByTestId('location-code').fill('A-01');
  const [locPost, locList] = await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
    waitForLocationsListGet(page),
    page.getByTestId('location-submit').click(),
  ]);
  expect(locPost.ok()).toBeTruthy();
  expect(locList.ok()).toBeTruthy();
  await expect(page.getByTestId('location-list').getByTestId('location-item')).toContainText('A-01');

  const sku = `SKU-E2E-${Date.now()}`;
  await page.getByTestId('product-name').fill('Коробка');
  await page.getByTestId('product-sku').fill(sku);
  await page.getByTestId('product-length-mm').fill('100');
  await page.getByTestId('product-width-mm').fill('200');
  await page.getByTestId('product-height-mm').fill('300');

  const [prodPost, prodList] = await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);
  expect(prodPost.ok()).toBeTruthy();
  expect(prodList.ok()).toBeTruthy();
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);

  const productRow = page.getByTestId('product-list').getByTestId('product-item').filter({ hasText: sku });
  await expect(productRow).toContainText('Коробка');
  await expect(productRow.getByTestId('product-volume')).toContainText('6');
});
