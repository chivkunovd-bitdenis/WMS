import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-NEW-001 — админ добавляет сотрудника ФФ, выдаёт права, первый вход с паролем.
test('admin adds FF staff user, toggles permissions, staff sets password on first login', async ({
  page,
}) => {
  const adminEmail = `e2e-staff-admin-${Date.now()}@example.com`;
  const staffEmail = `e2e-staff-user-${Date.now()}@example.com`;
  const staffPassword = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Staff Users');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await page.getByTestId('nav-ff-settings').click();
  await expect(page).toHaveURL(/\/app\/ff\/settings/);
  await expect(page.getByTestId('ff-staff-empty')).toBeVisible();

  await page.getByTestId('ff-staff-email').fill(staffEmail);
  await Promise.all([
    waitForPostOk(page, '/api/auth/staff-accounts'),
    waitForGetOk(page, '/api/auth/staff-accounts'),
    page.getByTestId('ff-staff-submit').click(),
  ]);
  await expect(page.getByTestId('ff-settings-users-success')).toContainText(staffEmail);
  const staffRow = page.getByTestId('ff-staff-row').filter({ hasText: staffEmail });
  await expect(staffRow).toBeVisible();

  const staffId = await staffRow.getAttribute('data-staff-id');
  expect(staffId).toBeTruthy();

  await Promise.all([
    waitForPatchOk(page, `/api/auth/staff-accounts/${staffId}/permissions`),
    staffRow.getByTestId(`ff-staff-perm-${staffId}-reception`).click(),
  ]);
  await expect(page.getByTestId('ff-staff-perm-saved')).toBeVisible();
  await Promise.all([
    waitForPatchOk(page, `/api/auth/staff-accounts/${staffId}/permissions`),
    staffRow.getByTestId(`ff-staff-perm-${staffId}-mp_shipments`).click(),
  ]);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.getByTestId('login-form').getByLabel('Email').fill(staffEmail);
  await page.getByTestId('login-form').getByLabel('Пароль').fill('');
  await Promise.all([
    page.waitForResponse((r) => {
      if (!r.url().includes('/api/auth/login')) {
        return false;
      }
      return r.status() === 200 || r.status() === 403;
    }),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);
  await expect(page.getByTestId('seller-password-setup-form')).toBeVisible();
  await page.getByTestId('seller-password-setup-form').getByLabel('Новый пароль').fill(staffPassword);
  await page.getByTestId('seller-password-setup-form').getByLabel('Повтор пароля').fill(staffPassword);
  await Promise.all([
    waitForPostOk(page, '/api/auth/set-initial-password'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('seller-password-setup-submit').click(),
  ]);

  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('nav-ff-reception')).toBeVisible();
  await expect(page.getByTestId('nav-ff-mp-shipments')).toBeVisible();
  await expect(page.getByTestId('nav-sellers')).toHaveCount(0);
  await expect(page.getByTestId('nav-ff-settings')).toHaveCount(0);
});
