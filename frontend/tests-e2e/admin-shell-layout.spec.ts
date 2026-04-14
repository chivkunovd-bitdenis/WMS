import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';

// TC-S15-001 — навигация по разделам после входа (целостность shell: один корень, ключевые области).
// TC-S02-001 — успешный вход в контекст сессии с видимым дашбордом.
test('admin shell: single app root, nav, dashboard and main sections visible', async ({ page }) => {
  const slug = `ff-shell-${Date.now()}`;
  const email = `e2e-shell-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('register-form')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('Shell Layout FF');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('app-root')).toHaveCount(1);
  await expect(page.getByTestId('app-section-nav')).toBeVisible();
  await expect(page.getByTestId('user-email')).toBeVisible();
  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('operations-section')).toBeVisible();
});
