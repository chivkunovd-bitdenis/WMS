import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S15-001 — навигация по разделам после входа (целостность shell: один корень, ключевые области).
// TC-S15-003 — дашборд ФФ: недельный календарь и пункт «Поставки и загрузки» в сайдбаре.
// TC-S02-001 — успешный вход в контекст сессии с видимым дашбордом.
test('admin shell: single app root, nav, dashboard and main sections visible', async ({ page }) => {
  const email = `e2e-shell-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('Shell Layout FF');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('app-sidebar')).toBeVisible();
  await expect(page.getByTestId('app-topbar')).toBeVisible();
  await expect(page.getByTestId('topbar-user')).toBeVisible();
  await expect(page.getByTestId('user-email')).toBeVisible();
  await expect(page.getByTestId('ff-week-calendar')).toBeVisible();
  await expect(page.getByTestId('nav-ff-supplies-shipments')).toBeVisible();

  await page.goto('/app/catalog');
  await expect(page.getByTestId('catalog-section')).toBeVisible();

  await page.goto('/app/ops');
  await expect(page.getByTestId('inbound-requests-table')).toBeVisible();
});
