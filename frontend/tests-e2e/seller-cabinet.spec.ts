import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
} from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-S12-001 — админ создаёт аккаунт селлера, привязанный к селлеру.
// TC-S12-002 — вход селлера: дашборд показывает контекст селлера.
// TC-S12-003 — селлер видит только свои списки (фильтрация по селлеру).
// TC-S03-003 — селлер не управляет складами в UI (формы создания скрыты).
// TC-S05-004 — селлер видит только разрешённые товары.
// TC-S12-004 — селлер создаёт draft inbound/outbound в пределах разрешений UI.
test('admin creates seller user; seller sees filtered catalog and inbound', async ({
  page,
}) => {
  const adminEmail = `e2e-sell-adm-${Date.now()}@example.com`;
  const sellerEmail = `e2e-sell-sl-${Date.now()}@example.com`;
  const skuA = `SKU-SELL-A-${Date.now()}`;
  const skuB = `SKU-SELL-B-${Date.now()}`;
  const whCode = `wh-sell-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller FF');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const token = regJson.access_token;
  const h = { Authorization: `Bearer ${token}` };

  const sA = await page.request.post('/api/sellers', { headers: h, data: { name: 'Brand A' } });
  expect(sA.ok()).toBeTruthy();
  const sellerAId = String(((await sA.json()) as { id: string }).id);
  const sB = await page.request.post('/api/sellers', { headers: h, data: { name: 'Brand B' } });
  expect(sB.ok()).toBeTruthy();
  const sellerBId = String(((await sB.json()) as { id: string }).id);

  const wh = await page.request.post('/api/warehouses', { headers: h, data: { name: 'WH', code: whCode } });
  expect(wh.ok()).toBeTruthy();
  const wid = String(((await wh.json()) as { id: string }).id);
  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, { headers: h, data: { code: 'L1' } });
  expect(loc.ok()).toBeTruthy();

  const prA = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'PA', sku_code: skuA, length_mm: 10, width_mm: 10, height_mm: 10, seller_id: sellerAId },
  });
  expect(prA.ok()).toBeTruthy();
  const prB = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'PB', sku_code: skuB, length_mm: 10, width_mm: 10, height_mm: 10, seller_id: sellerBId },
  });
  expect(prB.ok()).toBeTruthy();

  // Note: admin no longer creates inbound in UI (seller does).

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

  await page.getByTestId('nav-seller-products').click();
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  await expect(page.getByTestId('seller-product-row')).toHaveCount(1);
  await expect(page.getByTestId('seller-product-row').first()).toContainText(skuA);

  const baseIn = '/api/operations/inbound-intake-requests';
  await page.getByTestId('nav-seller-documents').click();
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await page.getByTestId('seller-create-inbound').click();
  await page.waitForURL('**/seller/inbound/new');
  await waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit'));
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible();
  await page.getByTestId('seller-inbound-add-products').click();
  await expect(page.getByTestId('seller-inbound-picker')).toBeVisible();
  await page.getByTestId('seller-inbound-picker-search').fill(skuA);
  await page.getByTestId('seller-inbound-picker-qty').first().fill('3');
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/lines')),
    page.getByTestId('seller-inbound-picker-apply').click(),
  ]);
  await expect(page.getByTestId('seller-inbound-line-row')).toHaveCount(1);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/submit')),
    page.getByTestId('seller-inbound-submit-warehouse').click(),
  ]);
  await expect(page.getByTestId('seller-documents-row')).toHaveCount(1);
});
