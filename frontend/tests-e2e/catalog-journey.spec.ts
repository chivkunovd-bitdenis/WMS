import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForLocationsListGet, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S03-001 — админ создаёт склад.
// TC-S03-002 — админ создаёт ячейку (локацию) в складе.
// TC-NEW-001 — печать штрихкода ячейки (превью содержит "Ячейка №" и barcode).
test('register then create warehouse and location with barcode print preview', async ({ page }) => {
  const email = `e2e-cat-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
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
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);

  await page.getByTestId('create-warehouse').click();
  await expect(page.getByTestId('warehouse-form')).toBeVisible();
  await page.getByTestId('warehouse-name').locator('input').fill('Основной');
  await page.getByTestId('warehouse-code').locator('input').fill('main-wh');

  const [whPost, whListAfterCreate] = await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('warehouse-submit').click(),
  ]);
  expect(whPost.ok()).toBeTruthy();
  expect(whListAfterCreate.ok()).toBeTruthy();
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);

  const createdWarehouseRow = page.getByTestId('warehouse-row').first();
  await expect(createdWarehouseRow).toContainText('Основной');
  await expect(createdWarehouseRow).toContainText('main-wh');
  await createdWarehouseRow.click();

  await expect(page.getByTestId('create-location')).toBeEnabled();
  await page.getByTestId('create-location').click();
  await expect(page.getByTestId('location-form')).toBeVisible();
  await page.getByTestId('location-code').locator('input').fill('A-01');
  const [locPost, locList] = await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
    waitForLocationsListGet(page),
    page.getByTestId('location-submit').click(),
  ]);
  expect(locPost.ok()).toBeTruthy();
  expect(locList.ok()).toBeTruthy();

  const locRow = page.getByTestId('location-row').filter({ hasText: 'A-01' });
  await expect(locRow).toBeVisible();

  const locJson = (await locPost.json()) as { barcode?: string };
  const locBarcode = String(locJson.barcode ?? '');
  expect(locBarcode).toMatch(/^LOC-[A-Z0-9]{12}$/);
  await expect(locRow).toContainText(locBarcode);

  await locRow.getByTestId('location-print').click();
  await expect(page.getByTestId('location-print-preview')).toBeVisible();
  await expect(page.getByTestId('location-print-preview')).toContainText('Ячейка № A-01');
  await expect(page.getByTestId('location-print-preview')).toContainText(locBarcode);
});
