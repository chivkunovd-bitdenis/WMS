import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-NEW-AUTH-01 — селлер на главном портале ФФ: вход отклонён с понятной ошибкой (не «тихий» сброс).
test('seller login on FF portal shows portal mismatch error', async ({ page }) => {
  const adminEmail = `e2e-portal-admin-${Date.now()}@example.com`;
  const sellerName = `Portal Brand ${Date.now()}`;
  const sellerEmail = `e2e-portal-seller-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('Portal Mismatch Org');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await page.getByTestId('nav-sellers').click();
  await page.getByTestId('seller-name').fill(sellerName);
  await page.getByTestId('seller-email').fill(sellerEmail);
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForPostOk(page, '/api/auth/seller-accounts'),
    page.getByTestId('seller-submit').click(),
  ]);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.getByTestId('login-form').getByLabel('Email').fill(sellerEmail);
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);

  await expect(page.getByTestId('login-form')).toBeVisible();
  await expect(page.getByTestId('auth-error')).toBeVisible();
  await expect(page.getByTestId('auth-error')).toContainText('/seller/');
  await expect(page.getByTestId('app-frame')).toHaveCount(0);
});
