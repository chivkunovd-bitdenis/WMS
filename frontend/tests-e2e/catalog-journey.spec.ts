import { test, expect } from '@playwright/test';

test('register then create warehouse, location, and product', async ({ page }) => {
  const slug = `ff-cat-${Date.now()}`;
  const email = `e2e-cat-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Catalog FF');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click();

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('catalog-section')).toBeVisible();

  await page.getByTestId('warehouse-name').fill('Основной');
  await page.getByTestId('warehouse-code').fill('main-wh');
  await page.getByTestId('warehouse-submit').click();

  await expect(page.getByTestId('warehouse-list').getByTestId('warehouse-item')).toContainText('main-wh');
  await expect(page.getByTestId('warehouse-list').getByTestId('warehouse-item')).toContainText('Основной');

  await page.getByTestId('location-code').fill('A-01');
  await page.getByTestId('location-submit').click();
  await expect(page.getByTestId('location-list').getByTestId('location-item')).toContainText('A-01');

  await page.getByTestId('product-name').fill('Коробка');
  await page.getByTestId('product-sku').fill(`SKU-E2E-${Date.now()}`);
  await page.getByTestId('product-length-mm').fill('100');
  await page.getByTestId('product-width-mm').fill('200');
  await page.getByTestId('product-height-mm').fill('300');
  await page.getByTestId('product-submit').click();

  const productRow = page.getByTestId('product-list').getByTestId('product-item').first();
  await expect(productRow).toContainText('Коробка');
  await expect(productRow.getByTestId('product-volume')).toContainText('6');
});
