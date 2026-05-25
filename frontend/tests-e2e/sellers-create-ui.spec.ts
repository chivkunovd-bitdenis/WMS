import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-S04-001 — запись селлера + учётка (email) в одной форме.
// TC-S12-001 — аккаунт привязан к селлеру; первый вход с пустым паролем.
test('admin creates seller with email; seller sets password on first login', async ({ page }) => {
  const email = `e2e-sel-ui-${Date.now()}@example.com`;
  const sellerName = `Brand ${Date.now()}`;
  const sellerEmail = `seller-${Date.now()}@example.com`;
  const sellerPassword = 'password123';

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
  await page.getByTestId('seller-email').fill(sellerEmail);
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForPostOk(page, '/api/auth/seller-accounts'),
    page.getByTestId('seller-submit').click(),
  ]);

  await expect(page.getByTestId('seller-create-success')).toContainText(sellerEmail);
  await expect(page.getByTestId('seller-row')).toContainText(sellerName);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await loginAsSeller(page, sellerEmail, sellerPassword, { firstTime: true });
  await expect(page.getByTestId('app-frame')).toBeVisible();
});
