import { test, expect } from '@playwright/test';

import { waitForDeleteOk, waitForGetOk, waitForPostOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

// TC-NEW-SELLER-STAFF-001 — seller owner creates a staff user with section permissions.
// TC-NEW-DELETE-DRAFTS-001 — seller can delete draft documents, with visible list update.
test('seller owner manages staff permissions and deletes draft documents only', async ({
  page,
}) => {
  const suffix = Date.now();
  const adminEmail = `e2e-seller-staff-admin-${suffix}@example.com`;
  const ownerEmail = `e2e-seller-owner-${suffix}@example.com`;
  const staffEmail = `e2e-seller-staff-${suffix}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller Staff');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const regJson = (await regRes.json()) as { access_token: string };
  const adminHeaders = { Authorization: `Bearer ${regJson.access_token}` };

  const seller = await page.request.post('/api/sellers', {
    headers: adminHeaders,
    data: { name: 'Seller Staff Brand' },
  });
  expect(seller.ok()).toBeTruthy();
  const sellerId = String(((await seller.json()) as { id: string }).id);

  const warehouse = await page.request.post('/api/warehouses', {
    headers: adminHeaders,
    data: { name: 'WH', code: `wh-seller-staff-${suffix}` },
  });
  expect(warehouse.ok()).toBeTruthy();
  const warehouseId = String(((await warehouse.json()) as { id: string }).id);

  const ownerAccount = await page.request.post('/api/auth/seller-accounts', {
    headers: adminHeaders,
    data: { seller_id: sellerId, email: ownerEmail, password },
  });
  expect(ownerAccount.ok()).toBeTruthy();

  const ownerLogin = await page.request.post('/api/auth/login', {
    data: { email: ownerEmail, password },
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
  await loginAsSeller(page, ownerEmail, password, { firstTime: false });
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  const draftRow = page.getByTestId('seller-documents-row').filter({ hasText: 'Черновик' });
  await expect(draftRow).toHaveCount(1);
  await Promise.all([
    waitForDeleteOk(page, '/api/operations/inbound-intake-requests'),
    draftRow.getByTestId('seller-delete-draft').click(),
  ]);
  await expect(page.getByTestId('seller-documents-delete-ok')).toContainText('Черновик удалён');
  await expect(page.getByTestId('seller-documents-row')).toHaveCount(0);

  await page.getByTestId('nav-seller-settings').click();
  await expect(page.getByTestId('seller-staff-panel')).toBeVisible();
  await expect(page.getByTestId('seller-staff-row').filter({ hasText: ownerEmail })).toBeVisible();
  await page.getByTestId('seller-staff-email').fill(staffEmail);
  await page.getByTestId('seller-staff-create-perm-products').click();
  await page.getByTestId('seller-staff-create-perm-honest_sign').click();
  await Promise.all([
    waitForPostOk(page, '/api/auth/seller-staff-accounts'),
    waitForGetOk(page, '/api/auth/seller-staff-accounts'),
    page.getByTestId('seller-staff-submit').click(),
  ]);
  await expect(page.getByTestId('seller-staff-ok')).toContainText(staffEmail);
  await expect(page.getByTestId('seller-staff-row').filter({ hasText: staffEmail })).toBeVisible();

  await page.getByTestId('logout').click();
  await loginAsSeller(page, staffEmail, password, { firstTime: true });
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible();
  await expect(page.getByTestId('nav-seller-products')).toHaveCount(0);
  await expect(page.getByTestId('nav-seller-honest-sign')).toHaveCount(0);
  await expect(page.getByTestId('nav-seller-settings')).toHaveCount(0);

  await page.goto('/seller/products');
  await expect(page.getByTestId('seller-access-denied')).toBeVisible();
});
