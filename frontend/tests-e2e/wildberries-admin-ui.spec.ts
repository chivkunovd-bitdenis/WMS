import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits';

test('admin saves WB tokens and runs cards sync job', async ({ page }) => {
  const slug = `ff-wb-${Date.now()}`;
  const email = `e2e-wb-${Date.now()}@example.com`;

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

  await Promise.all([
    waitForPostOk(page, '/api/operations/background-jobs'),
    page.getByTestId('wb-sync-cards').click(),
  ]);
  await expect(page.getByTestId('wb-sync-status')).toContainText('done', { timeout: 25_000 });
  await expect(page.getByTestId('wb-sync-result')).toContainText('Карточек получено: 1');
  await expect(page.getByTestId('wb-imported-cards-list')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('wb-imported-card-item').first()).toContainText('424242');
});
