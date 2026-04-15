import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
  waitForLocationsListGet,
} from './api-waits';

test('seller A outbound list excludes seller B shipments only (#11)', async ({ page }) => {
  const slug = `ff-sof-${Date.now()}`;
  const adminEmail = `e2e-sof-adm-${Date.now()}@example.com`;
  const sellerEmail = `e2e-sof-a-${Date.now()}@example.com`;
  const skuA = `SKU-SOF-A-${Date.now()}`;
  const skuB = `SKU-SOF-B-${Date.now()}`;
  const whCode = `wh-sof-${Date.now()}`;

  await page.goto('/');
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Outbound Filter');
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
  await page.getByTestId('inbound-line-qty').fill('10');
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

  await page.goto('/app/ops/inbound');
  await Promise.all([
    waitForPostOk(page, baseIn, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('inbound-create-submit').click(),
  ]);
  await page.getByTestId('inbound-line-product').selectOption({ label: `${skuB} — PB` });
  await page.getByTestId('inbound-line-qty').fill('10');
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

  const baseOut = '/api/operations/outbound-shipment-requests';
  await page.goto('/app/ops/outbound');

  await Promise.all([
    waitForPostOk(page, baseOut, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await page.getByTestId('outbound-line-product').selectOption({ label: `${skuB} — PB` });
  await page.getByTestId('outbound-line-qty').fill('1');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'L1' });
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
  ]);

  await page.goto('/app/ops/outbound');
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await page.getByTestId('outbound-line-product').selectOption({ label: `${skuA} — PA` });
  await page.getByTestId('outbound-line-qty').fill('1');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'L1' });
  await Promise.all([
    waitForPostOk(page, baseOut, (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
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
    waitForGetOk(page, '/api/operations/outbound-shipment-requests'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);

  await page.goto('/app/ops/outbound');
  const outboundItems = page.getByTestId('outbound-requests-list').getByTestId('outbound-request-item');
  await expect(outboundItems).toHaveCount(1);
  await outboundItems.first().click();
  await expect(page.getByTestId('outbound-detail')).toContainText(skuA);
  await expect(page.getByTestId('outbound-detail')).not.toContainText(skuB);
});
