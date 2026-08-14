import { test, expect, type Page } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

const INBOUND_API = '/api/operations/inbound-intake-requests';

async function createSubmittedSellerInbound(
  page: Page,
  sellerToken: string,
  warehouseId: string,
  productId: string,
): Promise<string> {
  const sellerHeaders = { Authorization: `Bearer ${sellerToken}` };
  const created = await page.request.post(INBOUND_API, {
    headers: sellerHeaders,
    data: { warehouse_id: warehouseId },
  });
  expect(created.ok()).toBeTruthy();
  const requestId = String(((await created.json()) as { id: string }).id);

  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers: { ...sellerHeaders, 'Content-Type': 'application/json' },
    data: { product_id: productId, expected_qty: 1 },
  });
  expect(line.ok()).toBeTruthy();

  const submitted = await page.request.post(`${INBOUND_API}/${requestId}/submit`, {
    headers: sellerHeaders,
  });
  expect(submitted.ok()).toBeTruthy();

  return requestId;
}

async function clientRouteTo(page: Page, path: string): Promise<void> {
  await page.evaluate((nextPath) => {
    window.history.pushState({}, '', nextPath);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
}

async function expectSellerInboundShell(page: Page, requestId: string): Promise<void> {
  await expect(page).toHaveTitle('WMS · Селлер');
  await expect(page.getByTestId('app-topbar')).toContainText('Портал селлера');
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible();
  expect(new URL(page.url()).pathname).toBe(`/seller/inbound/${requestId}`);
}

async function expectFfDeniedSellerProductsShell(page: Page, email: string): Promise<void> {
  await page.goto('/seller/products');
  await expect(page).toHaveTitle('WMS · Фулфилмент');
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('app-topbar')).toContainText('Портал ФФ');
  await expect(page.getByTestId('topbar-user')).toContainText(email);
  await expect(page.getByTestId('logout')).toBeVisible();
  await expect(page.getByTestId('ff-access-denied')).toContainText('Нет доступа к этому разделу.');
  await expect(page.getByTestId('login-form')).toHaveCount(0);
  await expect(page.getByTestId('nav-seller-products')).toHaveCount(0);
  await expect(page.getByTestId('seller-products-table')).toHaveCount(0);
}

async function createFulfillmentStaffToken(
  page: Page,
  adminHeaders: Record<string, string>,
  email: string,
  password: string,
): Promise<string> {
  const created = await page.request.post('/api/auth/staff-accounts', {
    headers: adminHeaders,
    data: { email },
  });
  expect(created.status()).toBe(201);

  const setup = await page.request.post('/api/auth/set-initial-password', {
    data: { email, password },
  });
  expect(setup.status()).toBe(200);

  const login = await page.request.post('/api/auth/login', {
    data: { email, password },
  });
  expect(login.status()).toBe(200);
  return String(((await login.json()) as { access_token: string }).access_token);
}

async function storeFulfillmentTokenOnly(page: Page, token: string): Promise<void> {
  await page.evaluate((nextToken) => {
    localStorage.setItem('wms_token_ff', nextToken);
    localStorage.removeItem('wms_token_seller');
    localStorage.removeItem('wms_token');
  }, token);
}

// TC-NEW-AUTH-03 — FF admin/staff direct seller deep route stays in FF shell without seller token.
test('FF admin and staff denied /seller/products stays in FF shell without seller token', async ({
  page,
}) => {
  const suffix = String(Date.now());
  const adminEmail = `e2e-ff-denied-admin-${suffix}@example.com`;
  const staffEmail = `e2e-ff-denied-staff-${suffix}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('FF Denied Seller Route Org');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [registerRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const adminToken = String(((await registerRes.json()) as { access_token: string }).access_token);
  await storeFulfillmentTokenOnly(page, adminToken);

  await expectFfDeniedSellerProductsShell(page, adminEmail);

  await page.goto('/seller/');
  await expect(page).toHaveTitle('WMS · Селлер');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await expect(page.getByTestId('app-frame')).toHaveCount(0);

  const staffToken = await createFulfillmentStaffToken(
    page,
    { Authorization: `Bearer ${adminToken}` },
    staffEmail,
    password,
  );
  await storeFulfillmentTokenOnly(page, staffToken);
  await expectFfDeniedSellerProductsShell(page, staffEmail);
});

// TC-NEW-AUTH-02 — FF и seller: два токена в localStorage, refresh не выбивает другой портал.
test('FF and seller sessions stay independent on reload and deep seller routes', async ({
  page,
}) => {
  const suffix = String(Date.now());
  const adminEmail = `e2e-dual-admin-${suffix}@example.com`;
  const sellerEmail = `e2e-dual-seller-${suffix}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('Dual Portal Org');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  await expect(page.getByTestId('app-frame')).toBeVisible();

  const ffTokenAfterRegister = await page.evaluate(() => localStorage.getItem('wms_token_ff'));
  expect(ffTokenAfterRegister).toBeTruthy();

  await page.getByTestId('nav-sellers').click();
  await page.getByTestId('seller-name').fill(`Brand ${suffix}`);
  await page.getByTestId('seller-email').fill(sellerEmail);
  const [createdSeller] = await Promise.all([
    waitForPostOk(page, '/api/sellers/with-account'),
    page.getByTestId('seller-submit').click(),
  ]);
  const sellerId = String(((await createdSeller.json()) as { seller_id: string }).seller_id);

  if (!ffTokenAfterRegister) {
    throw new Error('FF token missing after registration');
  }
  const ffHeaders = { Authorization: `Bearer ${ffTokenAfterRegister}` };
  const warehouse = await page.request.post('/api/warehouses', {
    headers: ffHeaders,
    data: { name: 'Dual Portal WH', code: `dual-${suffix}` },
  });
  expect(warehouse.ok()).toBeTruthy();
  const warehouseId = String(((await warehouse.json()) as { id: string }).id);

  const product = await page.request.post('/api/products', {
    headers: ffHeaders,
    data: {
      name: 'Dual Portal Product',
      sku_code: `dual-sku-${suffix}`,
      length_mm: 100,
      width_mm: 80,
      height_mm: 60,
      seller_id: sellerId,
    },
  });
  expect(product.ok()).toBeTruthy();
  const productId = String(((await product.json()) as { id: string }).id);

  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await expect(page.getByTestId('app-frame')).toBeVisible();

  const tokensAfterSellerLogin = await page.evaluate(() => ({
    ff: localStorage.getItem('wms_token_ff'),
    seller: localStorage.getItem('wms_token_seller'),
  }));
  expect(tokensAfterSellerLogin.ff).toBeTruthy();
  expect(tokensAfterSellerLogin.seller).toBeTruthy();
  expect(tokensAfterSellerLogin.ff).not.toBe(tokensAfterSellerLogin.seller);

  if (!tokensAfterSellerLogin.seller) {
    throw new Error('Seller token missing after login');
  }
  const requestId = await createSubmittedSellerInbound(
    page,
    tokensAfterSellerLogin.seller,
    warehouseId,
    productId,
  );

  await page.goto('/');
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await clientRouteTo(page, `/seller/inbound/${requestId}`);
  await expectSellerInboundShell(page, requestId);
  await page.reload();
  await expectSellerInboundShell(page, requestId);
  await page.getByTestId('nav-seller-documents').click();
  await expect.poll(() => new URL(page.url()).pathname).toBe('/seller/documents');
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  expect(new URL(page.url()).pathname).not.toBe('/documents');
  await page.goto('/seller/products');
  await expect(page.getByTestId('seller-products-table')).toBeVisible();
  await expect(page).toHaveTitle('WMS · Селлер');
  await expect(page.getByTestId('app-topbar')).toContainText('Портал селлера');
  await expect(page.getByTestId('login-form')).toHaveCount(0);

  await page.goto('/seller/');
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('login-form')).toHaveCount(0);

  await page.goto('/');
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.getByTestId('login-form')).toHaveCount(0);
});
