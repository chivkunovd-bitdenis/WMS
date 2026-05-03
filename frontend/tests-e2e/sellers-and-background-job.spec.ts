import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

/**
 * Реальный путь: экраны каталога и операций, кнопки, фоновая задача до статуса done.
 */
// TC-S04-001 — админ создаёт селлера.
// TC-S14-001 — жизненный цикл джобы movements digest (до done) с видимым результатом.
test('create seller, product with seller, run movements digest job', async ({ page }) => {
  const email = `e2e-sbj-${Date.now()}@example.com`;
  const sku = `SKU-SBJ-${Date.now()}`;
  const whCode = `wh-sbj-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E SB');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const token = regJson.access_token;
  const h = { Authorization: `Bearer ${token}` };

  const sellerRes = await page.request.post('/api/sellers', {
    headers: h,
    data: { name: 'ACME Seller' },
  });
  expect(sellerRes.ok()).toBeTruthy();
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  const whRes = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'WH', code: whCode },
  });
  expect(whRes.ok()).toBeTruthy();

  const prodRes = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Item', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10, seller_id: sellerId },
  });
  expect(prodRes.ok()).toBeTruthy();

  await page.goto('/app/ops/movements');
  await expect(page.getByTestId('background-job-section')).toBeVisible();
  const jobPost = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/api/operations/background-jobs') &&
      r.status() === 202,
  );
  await Promise.all([jobPost, page.getByTestId('background-job-start').click()]);
  await expect(page.getByTestId('background-job-status')).toContainText('done', { timeout: 25_000 });
  await expect(page.getByTestId('background-job-result')).toContainText('Всего движений');
});
