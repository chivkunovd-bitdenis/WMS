import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';

test('register then see dashboard', async ({ page }) => {
  const slug = `ff-e2e-${Date.now()}`;
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
  await expect(page.getByTestId('register-form')).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
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
  await expect(page.getByTestId('user-email')).toHaveText(email);
  await expect(page.getByTestId('org-name')).toHaveText('E2E FF');

  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('operations-section')).toBeVisible();
  await expect(page.getByTestId('warehouse-form')).toBeVisible();
  await expect(page.getByTestId('location-form')).toHaveCount(0);
  await expect(page.getByTestId('product-form')).toBeVisible();
  await expect(page.getByTestId('warehouse-submit')).toBeEnabled();
});
