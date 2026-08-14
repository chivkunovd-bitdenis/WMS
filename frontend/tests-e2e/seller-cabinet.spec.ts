import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPatchOk,
  waitForPostOk,
  waitForPutOk,
} from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

const e2eDbPath = fileURLToPath(new URL('../../backend/e2e.db', import.meta.url));

function sqliteUuid(id: string): string {
  return id.replaceAll('-', '').toLowerCase();
}

function allowSellerShop(userId: string, sellerId: string, enabled = false): void {
  execFileSync('sqlite3', [
    e2eDbPath,
    `insert into seller_shop_delegations (id, user_id, target_seller_id, enabled) values ('${sqliteUuid(randomUUID())}', '${sqliteUuid(userId)}', '${sqliteUuid(sellerId)}', ${enabled ? 1 : 0})`,
  ]);
}

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
  const skuA2 = `SKU-SELL-A2-${Date.now()}`;
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
  const productAId = String(((await prA.json()) as { id: string }).id);
  const prA2 = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'PA2', sku_code: skuA2, length_mm: 10, width_mm: 10, height_mm: 10, seller_id: sellerAId },
  });
  expect(prA2.ok()).toBeTruthy();
  const productA2Id = String(((await prA2.json()) as { id: string }).id);
  const prB = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'PB', sku_code: skuB, length_mm: 10, width_mm: 10, height_mm: 10, seller_id: sellerBId },
  });
  expect(prB.ok()).toBeTruthy();

  // Note: admin no longer creates inbound in UI (seller does).

  const acc = await page.request.post('/api/auth/seller-accounts', {
    headers: h,
    data: { seller_id: sellerAId, email: sellerEmail },
  });
  expect(acc.ok()).toBeTruthy();

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await loginAsSeller(page, sellerEmail, 'password123', { firstTime: true });
  await page.waitForURL('**/seller/**');

  await page.getByTestId('nav-seller-products').click();
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  await expect(page.getByTestId('seller-product-row')).toHaveCount(2);
  await expect(page.getByTestId('seller-product-row').filter({ hasText: skuA })).toBeVisible();
  await expect(page.getByTestId('seller-product-row').filter({ hasText: skuA2 })).toBeVisible();
  await expect(page.getByTestId('seller-product-row').filter({ hasText: skuB })).toHaveCount(0);
  await expect(page.getByTestId('seller-products-bulk-honest-sign')).toBeDisabled();

  await page.getByTestId('seller-products-select-all').click();
  await expect(page.getByTestId('seller-products-bulk-honest-sign')).toBeEnabled();
  await Promise.all([
    waitForPatchOk(page, '/api/products/requires-honest-sign/bulk'),
    page.getByTestId('seller-products-bulk-honest-sign').click(),
  ]);
  await expect(page.getByTestId('seller-products-notice')).toContainText('Честный знак включён');
  await expect(page.getByTestId(`seller-honest-sign-status-${productAId}`)).toBeVisible();
  await expect(page.getByTestId(`seller-honest-sign-status-${productA2Id}`)).toBeVisible();

  const sellerToken = await page.evaluate(() => localStorage.getItem('wms_token_seller'));
  expect(sellerToken).toBeTruthy();
  const sellerCatalog = await page.request.get('/api/products/wb-catalog', {
    headers: { Authorization: `Bearer ${sellerToken}` },
  });
  expect(sellerCatalog.ok()).toBeTruthy();
  const sellerCatalogById = new Map(
    ((await sellerCatalog.json()) as { id: string; requires_honest_sign: boolean }[]).map((row) => [
      row.id,
      row,
    ]),
  );
  expect(sellerCatalogById.get(productAId)?.requires_honest_sign).toBe(true);
  expect(sellerCatalogById.get(productA2Id)?.requires_honest_sign).toBe(true);

  const baseIn = '/api/operations/inbound-intake-requests';
  await page.getByTestId('nav-seller-documents').click();
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await page.getByTestId('seller-create-inbound').click();
  await page.waitForURL('**/seller/inbound/new**');
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

// TC-NEW-SELLER-SCOPE-001 — shop manager sees only products of the active allowed seller.
test('seller shop manager switches allowed seller without seeing forbidden products', async ({
  page,
}) => {
  const suffix = Date.now();
  const adminEmail = `e2e-scope-admin-${suffix}@example.com`;
  const managerEmail = `vitalik-e2e-${suffix}@mail.ru`;
  const password = 'password123';
  const skuHome = `SCOPE-HOME-${suffix}`;
  const skuAllowed = `SCOPE-ALLOWED-${suffix}`;
  const skuForbidden = `SCOPE-FORBIDDEN-${suffix}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller Scope');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const adminToken = String(((await regRes.json()) as { access_token: string }).access_token);
  const h = { Authorization: `Bearer ${adminToken}` };

  const home = await page.request.post('/api/sellers/with-account', {
    headers: h,
    data: { name: 'Home Scope Shop', email: managerEmail, password },
  });
  expect(home.ok()).toBeTruthy();
  const homeJson = (await home.json()) as { seller_id: string; user_id: string };
  const homeSellerId = String(homeJson.seller_id);
  const homeUserId = String(homeJson.user_id);
  const allowed = await page.request.post('/api/sellers', {
    headers: h,
    data: { name: 'Allowed Scope Shop' },
  });
  expect(allowed.ok()).toBeTruthy();
  const allowedSellerId = String(((await allowed.json()) as { id: string }).id);
  const forbidden = await page.request.post('/api/sellers', {
    headers: h,
    data: { name: 'Forbidden Scope Shop' },
  });
  expect(forbidden.ok()).toBeTruthy();
  const forbiddenSellerId = String(((await forbidden.json()) as { id: string }).id);

  allowSellerShop(homeUserId, allowedSellerId, false);

  for (const [sellerId, sku, name] of [
    [homeSellerId, skuHome, 'Home Scope Product'],
    [allowedSellerId, skuAllowed, 'Allowed Scope Product'],
    [forbiddenSellerId, skuForbidden, 'Forbidden Scope Product'],
  ]) {
    const product = await page.request.post('/api/products', {
      headers: h,
      data: {
        name,
        sku_code: sku,
        length_mm: 10,
        width_mm: 10,
        height_mm: 10,
        seller_id: sellerId,
      },
    });
    expect(product.ok()).toBeTruthy();
  }

  await page.getByTestId('logout').click();
  await loginAsSeller(page, managerEmail, password, { firstTime: false });
  await expect(page.getByTestId('seller-shops-panel')).toBeVisible();
  await expect(page.getByTestId(`seller-shop-check-${allowedSellerId}`)).toBeVisible();
  await expect(page.getByTestId(`seller-shop-check-${forbiddenSellerId}`)).toHaveCount(0);
  await expect(page.getByTestId('seller-shops-checklist')).not.toContainText('Forbidden Scope Shop');

  await page.getByTestId('nav-seller-products').click();
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  await expect(page.getByTestId('seller-products-table')).toContainText(skuHome);
  await expect(page.getByTestId('seller-products-table')).not.toContainText(skuAllowed);
  await expect(page.getByTestId('seller-products-table')).not.toContainText(skuForbidden);

  await Promise.all([
    waitForPutOk(page, '/api/auth/seller-shops'),
    page.getByTestId(`seller-shop-check-${allowedSellerId}`).click(),
  ]);
  await Promise.all([
    waitForPostOk(page, '/api/auth/switch-seller'),
    page.getByTestId(`seller-shop-switch-${allowedSellerId}`).click(),
  ]);
  await page.getByTestId('nav-seller-products').click();
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  await expect(page.getByTestId('seller-products-table')).toContainText(skuAllowed);
  await expect(page.getByTestId('seller-products-table')).not.toContainText(skuHome);
  await expect(page.getByTestId('seller-products-table')).not.toContainText(skuForbidden);
});
