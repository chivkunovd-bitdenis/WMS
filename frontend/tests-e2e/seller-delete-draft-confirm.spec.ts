import { test, expect } from '@playwright/test';

import { waitForDeleteOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-NEW-F15-SELLER-DRAFT-CONFIRM — seller draft delete requires explicit confirmation.
test('seller draft delete asks for confirmation before removing the document', async ({ page }) => {
  const suffix = Date.now();
  const adminEmail = `e2e-f15-delete-admin-${suffix}@example.com`;
  const sellerEmail = `e2e-f15-delete-seller-${suffix}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E F15 Delete');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const adminHeaders = { Authorization: `Bearer ${regJson.access_token}` };

  const seller = await page.request.post('/api/sellers', {
    headers: adminHeaders,
    data: { name: 'F15 Delete Seller' },
  });
  expect(seller.ok()).toBeTruthy();
  const sellerId = String(((await seller.json()) as { id: string }).id);

  const warehouse = await page.request.post('/api/warehouses', {
    headers: adminHeaders,
    data: { name: 'F15 Delete WH', code: `f15-delete-${suffix}` },
  });
  expect(warehouse.ok()).toBeTruthy();
  const warehouseId = String(((await warehouse.json()) as { id: string }).id);

  const account = await page.request.post('/api/auth/seller-accounts', {
    headers: adminHeaders,
    data: { seller_id: sellerId, email: sellerEmail, password },
  });
  expect(account.ok()).toBeTruthy();

  const ownerLogin = await page.request.post('/api/auth/login', {
    data: { email: sellerEmail, password },
  });
  expect(ownerLogin.ok()).toBeTruthy();
  const ownerToken = String(((await ownerLogin.json()) as { access_token: string }).access_token);
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` };

  const draft = await page.request.post('/api/operations/inbound-intake-requests', {
    headers: ownerHeaders,
    data: { warehouse_id: warehouseId },
  });
  expect(draft.ok()).toBeTruthy();

  await page.getByTestId('logout').click();
  await loginAsSeller(page, sellerEmail, password, { firstTime: false });
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  const draftRow = page.getByTestId('seller-documents-row').filter({ hasText: 'Черновик' });
  await expect(draftRow).toHaveCount(1);

  await draftRow.getByTestId('seller-delete-draft').click();
  await expect(page.getByTestId('seller-delete-draft-confirm-dialog')).toBeVisible();
  await page.getByTestId('seller-delete-draft-cancel').click();
  await expect(page.getByTestId('seller-delete-draft-confirm-dialog')).toHaveCount(0);
  await expect(draftRow).toHaveCount(1);

  await draftRow.getByTestId('seller-delete-draft').click();
  await expect(page.getByTestId('seller-delete-draft-confirm-dialog')).toBeVisible();
  await Promise.all([
    waitForDeleteOk(page, '/api/operations/inbound-intake-requests'),
    page.getByTestId('seller-delete-draft-confirm').click(),
  ]);
  await expect(page.getByTestId('seller-documents-delete-ok')).toContainText('Черновик удалён');
  await expect(page.getByTestId('seller-documents-row')).toHaveCount(0);
});
