import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S04-001 — админ создаёт запись селлера через UI.
test('admin creates seller record from sellers screen', async ({ page }) => {
  const email = `e2e-sel-ui-${Date.now()}@example.com`;
  const sellerName = `Brand ${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sellers UI');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await page.getByTestId('nav-sellers').click();
  await expect(page).toHaveURL(/\/app\/ff\/sellers$/);
  await expect(page.getByTestId('sellers-empty')).toBeVisible();

  await page.getByTestId('seller-name').fill(sellerName);
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    page.getByTestId('seller-submit').click(),
  ]);

  await expect(page.getByTestId('sellers-empty')).toHaveCount(0);
  await expect(page.getByTestId('seller-row')).toContainText(sellerName);
});
