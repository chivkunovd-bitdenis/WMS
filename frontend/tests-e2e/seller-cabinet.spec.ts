import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
  waitForPatchOk,
  waitForLocationsListGet,
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
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await page.goto('/app/catalog');
  await page.getByTestId('seller-name').fill('Brand A');
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForGetOk(page, '/api/sellers'),
    page.getByTestId('seller-submit').click(),
  ]);
  await page.getByTestId('seller-name').fill('Brand B');
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

  await page.getByTestId('product-name').fill('PA');
  await page.getByTestId('product-sku').fill(skuA);
  await page.getByTestId('product-length-mm').fill('10');
  await page.getByTestId('product-width-mm').fill('10');
  await page.getByTestId('product-height-mm').fill('10');
  await page.getByTestId('product-seller').selectOption({ label: 'Brand A' });
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);

  await page.getByTestId('product-name').fill('PB');
  await page.getByTestId('product-sku').fill(skuB);
  await page.getByTestId('product-length-mm').fill('10');
  await page.getByTestId('product-width-mm').fill('10');
  await page.getByTestId('product-height-mm').fill('10');
  await page.getByTestId('product-seller').selectOption({ label: 'Brand B' });
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);

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
