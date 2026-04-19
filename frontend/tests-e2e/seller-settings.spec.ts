import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk, waitForLocationsListGet } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-NEW-SELLER-SETTINGS-001 — seller can save WB Content API key (validated by cards list).
test('seller settings: save WB content api key', async ({ page }) => {
  const adminEmail = `e2e-set-adm-${Date.now()}@example.com`;
  const sellerEmail = `e2e-set-sl-${Date.now()}@example.com`;
  const whCode = `wh-set-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Settings');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form')
      .getByRole('button', { name: 'Создать аккаунт' })
      .click(),
  ]);

  await page.goto('/app/catalog');
  await page.getByTestId('seller-name').fill('Brand A');
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForGetOk(page, '/api/sellers'),
    page.getByTestId('seller-submit').click(),
  ]);

  await page.getByTestId('warehouse-name').fill('WH');
  await page.getByTestId('warehouse-code').fill(whCode);
  await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
    waitForGetOk(page, '/api/warehouses'),
    page.getByTestId('warehouse-submit').click(),
  ]);
  await page.getByTestId('warehouse-list').getByTestId('warehouse-item').first().click();
  await page.getByTestId('location-code').fill('L1');
  await Promise.all([
    waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
    waitForLocationsListGet(page),
    page.getByTestId('location-submit').click(),
  ]);

  await page.goto('/app/dashboard');
  await page.getByTestId('seller-account-seller').selectOption({ label: 'Brand A' });
  await page.getByTestId('seller-account-email').fill(sellerEmail);
  await Promise.all([
    waitForPostOk(page, '/api/auth/seller-accounts'),
    page.getByTestId('seller-account-submit').click(),
  ]);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await loginAsSeller(page, sellerEmail, 'password123', { firstTime: true });
  await page.waitForURL('**/seller/**');

  await page.getByTestId('nav-seller-settings').click();
  await expect(page.getByTestId('seller-settings-wb-card')).toBeVisible();
  await page.getByTestId('seller-settings-add-key').click();
  await expect(page.getByTestId('seller-settings-key-dialog')).toBeVisible();
  await page.getByTestId('seller-settings-key-input').fill('dummy-key');
  await Promise.all([
    waitForPostOk(page, '/api/integrations/wildberries/self/content-token'),
    page.getByTestId('seller-settings-save').click(),
  ]);
  await expect(page.getByTestId('seller-settings-ok')).toBeVisible();

  // After save, settings should show that key is added (gray status).
  await expect(page.getByTestId('seller-settings-key-status')).toContainText('добавлен');
});

