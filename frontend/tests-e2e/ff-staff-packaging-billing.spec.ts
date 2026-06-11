import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-NEW-002 — админ задаёт ставку за упаковку и видит колонки расчёта ЗП.
test('admin sets staff packaging rate and sees billing columns', async ({ page }) => {
  const adminEmail = `e2e-bill-admin-${Date.now()}@example.com`;
  const staffEmail = `e2e-bill-staff-${Date.now()}@example.com`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Staff Billing');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/register') && r.ok()),
    page.waitForResponse((r) => r.url().includes('/api/auth/me') && r.ok()),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await page.getByTestId('nav-ff-settings').click();
  await expect(page.getByTestId('ff-staff-billing-month')).toBeVisible();

  await page.getByTestId('ff-staff-email').fill(staffEmail);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/staff-accounts') && r.request().method() === 'POST' && r.ok()),
    page.waitForResponse((r) => r.url().includes('/api/auth/staff-accounts') && r.request().method() === 'GET' && r.ok()),
    page.getByTestId('ff-staff-submit').click(),
  ]);

  const staffRow = page.getByTestId('ff-staff-row').filter({ hasText: staffEmail });
  await expect(staffRow).toBeVisible();
  const staffId = await staffRow.getAttribute('data-staff-id');
  expect(staffId).toBeTruthy();

  const rateInput = page.getByTestId(`ff-staff-rate-${staffId}`);
  await rateInput.fill('12.5');
  await Promise.all([
    waitForPatchOk(page, `/api/auth/staff-accounts/${staffId}/packaging-rate`),
    rateInput.blur(),
  ]);
  await expect(page.getByTestId('ff-staff-rate-saved')).toBeVisible();
  await expect(page.getByTestId(`ff-staff-units-${staffId}`)).toHaveText('0');
  await expect(page.getByTestId(`ff-staff-earned-${staffId}`)).toHaveText('0');
});
