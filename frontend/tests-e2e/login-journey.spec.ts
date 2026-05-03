import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S02-001 — после регистрации и повторного входа каталог доступен (API + UI).
test('logout then login reaches catalog UI and loads catalog via API', async ({ page }) => {
  const email = `e2e-login-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('Login Journey FF');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password);

  const [loginRes, meAfterLogin, whListRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    waitForGetOk(page, '/api/auth/me'),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);
  expect(loginRes.ok()).toBeTruthy();
  expect(meAfterLogin.ok()).toBeTruthy();
  expect(whListRes.ok()).toBeTruthy();

  await page.goto('/app/catalog');
  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('warehouses-panel')).toBeVisible();
  await expect(page.getByTestId('locations-panel')).toBeVisible();
  await expect(page.getByTestId('create-warehouse')).toBeVisible();
  // No warehouse selected yet in empty state -> create location is disabled.
  await expect(page.getByTestId('create-location')).toBeDisabled();
  await expect(page.getByTestId('catalog-error')).toHaveCount(0);
});
