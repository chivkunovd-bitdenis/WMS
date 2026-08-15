import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-NEW-CAL-01 — FF календарь отгрузок: основной экран показывает сетку дней без dashboard-таблиц.
// Given: админ ФФ; When: открывает основной экран; Then: видит именно календарную сетку дней, без старых dashboard-блоков.
test('fulfillment admin sees shipment calendar and supplies-shipments page', async ({ page }) => {
  const email = `e2e-ff-dash-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Dashboard');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('cal-01-title')).toContainText('Календарь отгрузок');
  await expect(page.getByTestId('ff-week-calendar')).toBeVisible();
  await expect(page.getByTestId('ff-dashboard-inbound-block')).toHaveCount(0);
  await expect(page.getByTestId('ff-dashboard-outbound-block')).toHaveCount(0);
  await expect(page.getByTestId('cal-01-grid')).toBeVisible();
  await expect(page.getByTestId('cal-01-weekday')).toHaveCount(7);
  await expect(await page.locator('[data-testid^="cal-01-day-"]').count()).toBeGreaterThan(27);

  await page.getByTestId('nav-dashboard').click();
  await expect(page.getByTestId('cal-01-title')).toContainText('Календарь отгрузок');
});
