import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits';

test('admin saves WB tokens, syncs cards and supplies, links SKU', async ({ page }) => {
  const slug = `ff-wb-${Date.now()}`;
  const email = `e2e-wb-${Date.now()}@example.com`;
  const linkSku = `SKU-WB-LINK-${Date.now()}`;

  await page.goto('/');
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E WB Org');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('sellers-section')).toBeVisible();
  await page.getByTestId('seller-name').fill('WB Seller Co');
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    waitForGetOk(page, '/api/sellers'),
    page.getByTestId('seller-submit').click(),
  ]);

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

  await page.getByTestId('product-name').fill('WB link item');
  await page.getByTestId('product-sku').fill(linkSku);
  await page.getByTestId('product-length-mm').fill('10');
  await page.getByTestId('product-width-mm').fill('10');
  await page.getByTestId('product-height-mm').fill('10');
  await page.getByTestId('product-seller').selectOption({ label: 'WB Seller Co' });
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('product-submit').click(),
  ]);

  await page.getByTestId('wb-link-product-id').selectOption({ label: `${linkSku} — WB link item` });
  await page.getByTestId('wb-link-nm-id').fill('424242');
  await Promise.all([
    waitForPostOk(page, '/api/integrations/wildberries/sellers', (u) => u.includes('link-product')),
    waitForGetOk(page, '/api/products'),
    page.getByTestId('wb-link-submit').click(),
  ]);
  const prodRow = page
    .getByTestId('product-list')
    .getByTestId('product-item')
    .filter({ hasText: linkSku });
  await expect(prodRow.getByTestId('product-wb-nm')).toContainText('424242');
});
