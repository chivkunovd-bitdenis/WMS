import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';
import { createSellerAccountViaApi } from './seller-account-helpers';

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
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form')
      .getByRole('button', { name: 'Создать аккаунт' })
      .click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const token = regJson.access_token;
  const h = { Authorization: `Bearer ${token}` };

  const sA = await page.request.post('/api/sellers', { headers: h, data: { name: 'Brand A' } });
  expect(sA.ok()).toBeTruthy();
  const sellerAId = String(((await sA.json()) as { id: string }).id);

  const wh = await page.request.post('/api/warehouses', { headers: h, data: { name: 'WH', code: whCode } });
  expect(wh.ok()).toBeTruthy();
  const wid = String(((await wh.json()) as { id: string }).id);
  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, { headers: h, data: { code: 'L1' } });
  expect(loc.ok()).toBeTruthy();

  await createSellerAccountViaApi(page.request, h, sellerAId, sellerEmail);

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

