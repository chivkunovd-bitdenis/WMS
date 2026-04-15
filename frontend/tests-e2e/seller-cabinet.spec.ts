import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
  waitForLocationsListGet,
} from './api-waits';

// TC-S12-001 — админ создаёт аккаунт селлера, привязанный к селлеру.
// TC-S12-002 — вход селлера: дашборд показывает контекст селлера.
// TC-S12-003 — селлер видит только свои списки (фильтрация по селлеру).
// TC-S03-003 — селлер не управляет складами в UI (формы создания скрыты).
// TC-S05-004 — селлер видит только разрешённые товары.
// TC-S12-004 — селлер создаёт draft inbound/outbound в пределах разрешений UI.
test('admin creates seller user; seller sees filtered catalog and inbound', async ({
  page,
}) => {
  const slug = `ff-sell-${Date.now()}`;
  const adminEmail = `e2e-sell-adm-${Date.now()}@example.com`;
  const sellerEmail = `e2e-sell-sl-${Date.now()}@example.com`;
  const skuA = `SKU-SELL-A-${Date.now()}`;
  const skuB = `SKU-SELL-B-${Date.now()}`;
  const whCode = `wh-sell-${Date.now()}`;

  await page.goto('/');
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller FF');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(adminEmail);
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

  const baseIn = '/api/operations/inbound-intake-requests';
  await page.goto('/app/ops/inbound');
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('inbound-create-submit').click(),
  ]);
  await page.getByTestId('inbound-line-product').selectOption({ label: `${skuA} — PA` });
  await page.getByTestId('inbound-line-qty').fill('8');
  await page.getByTestId('inbound-line-location').selectOption({ label: 'L1' });
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/lines')),
    page.getByTestId('inbound-line-submit').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/submit')),
    page.getByTestId('inbound-submit-request').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/post')),
    page.getByTestId('inbound-post-submit').click(),
  ]);

  await page.goto('/app/dashboard');
  await page.getByTestId('seller-account-seller').selectOption({ label: 'Brand A' });
  await page.getByTestId('seller-account-email').fill(sellerEmail);
  await page.getByTestId('seller-account-password').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/seller-accounts'),
    page.getByTestId('seller-account-submit').click(),
  ]);

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.getByTestId('login-form').getByLabel('Email').fill(sellerEmail);
  await page.getByTestId('login-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    waitForGetOk(page, '/api/auth/me'),
    waitForGetOk(page, '/api/products'),
    waitForGetOk(page, '/api/operations/inbound-intake-requests'),
    waitForGetOk(page, '/api/operations/outbound-shipment-requests'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);

  await page.goto('/app/catalog');
  await expect(page.getByTestId('seller-cabinet-notice')).toBeVisible();
  await expect(page.getByTestId('warehouse-form')).toHaveCount(0);
  await expect(page.getByTestId('product-item')).toHaveCount(1);
  await expect(page.getByTestId('product-list').getByTestId('product-item').first()).toContainText(
    skuA,
  );

  await page.goto('/app/dashboard');
  await expect(page.getByTestId('seller-cabinet-label')).toContainText('Brand A');

  await page.goto('/app/ops/inbound');
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('inbound-create-submit').click(),
  ]);
  await expect(page.getByTestId('inbound-detail-status')).toContainText('draft');
  await page.getByTestId('inbound-line-product').selectOption({ label: `${skuA} — PA` });
  await page.getByTestId('inbound-line-qty').fill('3');
  await page.getByTestId('inbound-line-location').selectOption({ label: 'L1' });
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => u.includes('/lines')),
    page.getByTestId('inbound-line-submit').click(),
  ]);
  await expect(page.getByTestId('inbound-requests-list').getByTestId('inbound-request-item')).toHaveCount(
    2,
  );
  await expect(page.getByTestId('inbound-detail-lines').getByTestId('inbound-detail-line')).toHaveCount(1);

  const baseOut = '/api/operations/outbound-shipment-requests';
  await page.goto('/app/ops/outbound');
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('draft');
  await page.getByTestId('outbound-line-product').selectOption({ label: `${skuA} — PA` });
  await page.getByTestId('outbound-line-qty').fill('2');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'L1' });
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
  ]);
  await expect(
    page.getByTestId('outbound-requests-list').getByTestId('outbound-request-item'),
  ).toHaveCount(1);
  await expect(
    page.getByTestId('outbound-detail-lines').getByTestId('outbound-detail-line'),
  ).toHaveCount(1);
});
