import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-S11-002, TC-S11-003, TC-S11-004, TC-S11-006 — токены WB, синхронизация, привязка SKU.
test('admin saves WB tokens, syncs cards and supplies, links SKU', async ({ page }) => {
  const email = `e2e-wb-${Date.now()}@example.com`;
  const linkSku = `SKU-WB-LINK-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E WB Org');
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
    data: { name: 'WB Seller Co' },
  });
  expect(sellerRes.ok()).toBeTruthy();
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  await page.goto('/app/integrations/wb');
  await expect(page.getByTestId('wildberries-integration-section')).toBeVisible();
  await expect(page.getByTestId('wb-token-flags')).toContainText('нет токена');

  await page.getByTestId('wb-content-token').fill('e2e-placeholder-wb-token');
  await Promise.all([
    waitForPatchOk(page, '/api/integrations/wildberries/sellers', (u) =>
      u.includes('/tokens'),
    ),
    page.getByTestId('wb-save-tokens').click(),
  ]);
  await expect(page.getByTestId('wb-token-flags')).toContainText('Контент API: токен есть');

  await page.getByTestId('wb-supplies-token').fill('e2e-placeholder-wb-supplies');
  await Promise.all([
    waitForPatchOk(page, '/api/integrations/wildberries/sellers', (u) => u.includes('/tokens')),
    page.getByTestId('wb-save-tokens').click(),
  ]);
  await expect(page.getByTestId('wb-token-flags')).toContainText('Поставки API: токен есть');

  await Promise.all([
    waitForPostOk(page, '/api/operations/background-jobs'),
    page.getByTestId('wb-sync-cards').click(),
  ]);
  await expect(page.getByTestId('wb-sync-status')).toContainText('done', { timeout: 25_000 });
  await expect(page.getByTestId('wb-sync-result')).toContainText('Карточек получено: 1');
  await expect(page.getByTestId('wb-imported-cards-list')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('wb-imported-card-item').first()).toContainText('424242');

  await Promise.all([
    waitForPostOk(page, '/api/operations/background-jobs'),
    page.getByTestId('wb-sync-supplies').click(),
  ]);
  await expect(page.getByTestId('wb-supplies-sync-status')).toContainText('done', { timeout: 25_000 });
  await expect(page.getByTestId('wb-supplies-sync-result')).toContainText(
    'Поставок получено: 1, сохранено: 1',
  );
  await expect(page.getByTestId('wb-imported-supplies-list')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('wb-imported-supply-item').first()).toContainText('888001');

  const prodRes = await page.request.post('/api/products', {
    headers: h,
    data: {
      name: 'WB link item',
      sku_code: linkSku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    },
  });
  expect(prodRes.ok()).toBeTruthy();

  await page.goto('/app/integrations/wb');
  await page.getByTestId('wb-link-product-id').selectOption({ label: `${linkSku} — WB link item` });
  await page.getByTestId('wb-link-nm-id').fill('424242');
  const [linkRes, prodListAfter] = await Promise.all([
    waitForPostOk(page, '/api/integrations/wildberries/sellers', (u) => u.includes('link-product')),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('wb-link-submit').click(),
  ]);
  expect(linkRes.ok()).toBeTruthy();
  expect(prodListAfter.ok()).toBeTruthy();
  const prodListJson = (await prodListAfter.json()) as Array<{
    sku_code: string;
    wb_nm_id?: number | null;
  }>;
  const linked = prodListJson.find((p) => p.sku_code === linkSku) ?? null;
  expect(linked?.wb_nm_id).toBe(424242);
});
