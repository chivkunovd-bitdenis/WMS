import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S01-001 — успешная регистрация (админ) с переходом на дашборд.
// TC-S15-001 — навигация по разделам после входа.
test('register then see dashboard', async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');

  const [registerRes, meRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  expect(registerRes.ok()).toBeTruthy();
  expect(meRes.ok()).toBeTruthy();

  await expect(page.getByTestId('auth-error')).toHaveCount(0);
  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('app-sidebar')).toBeVisible();
  await expect(page.getByTestId('user-email')).toHaveText(email);
  await expect(page.getByTestId('org-name')).toHaveText('E2E FF');

  await page.goto('/app/catalog');
  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('warehouse-form')).toBeVisible();
  await expect(page.getByTestId('location-form')).toHaveCount(0);
  await expect(page.getByTestId('product-form')).toBeVisible();
  await expect(page.getByTestId('warehouse-submit')).toBeEnabled();
});
