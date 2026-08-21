import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// J02-C1-01 — expiry clears only the selected portal session.
test('expired seller session does not clear the fulfillment session', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('wms_token_ff', 'valid-ff-session');
    localStorage.setItem('wms_token_seller', 'expired-seller-session');
  });
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/auth/me') && route.request().headers().authorization?.includes('expired-seller-session')) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'invalid_token' }),
      });
      return;
    }
    if (path.endsWith('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'seller-e2e@example.com',
          organization_name: 'Local E2E Seller',
          role: 'fulfillment_seller',
          seller_id: 'seller-e2e',
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.goto('/seller/');
  await expect(page.getByTestId('session-expired-notice')).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => ({
      ff: localStorage.getItem('wms_token_ff'),
      seller: localStorage.getItem('wms_token_seller'),
    })))
    .toEqual({ ff: 'valid-ff-session', seller: null });
});

// TC-NEW-AUTH-02 — FF и seller: два токена в localStorage, refresh не выбивает другой портал.
test('FF and seller sessions stay independent after login and page reload', async ({
  page,
}) => {
  const adminEmail = `e2e-dual-admin-${Date.now()}@example.com`;
  const sellerEmail = `e2e-dual-seller-${Date.now()}@example.com`;
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
  await page.getByTestId('seller-name').fill(`Brand ${Date.now()}`);
  await page.getByTestId('seller-email').fill(sellerEmail);
  await Promise.all([
    waitForPostOk(page, '/api/sellers/with-account'),
    page.getByTestId('seller-submit').click(),
  ]);

  await loginAsSeller(page, sellerEmail, password, { firstTime: true });
  await expect(page.getByTestId('app-frame')).toBeVisible();

  const tokensAfterSellerLogin = await page.evaluate(() => ({
    ff: localStorage.getItem('wms_token_ff'),
    seller: localStorage.getItem('wms_token_seller'),
  }));
  expect(tokensAfterSellerLogin.ff).toBeTruthy();
  expect(tokensAfterSellerLogin.seller).toBeTruthy();
  expect(tokensAfterSellerLogin.ff).not.toBe(tokensAfterSellerLogin.seller);

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
