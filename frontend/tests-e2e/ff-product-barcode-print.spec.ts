import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { INBOUND_API, loginFfAdmin } from './inbound-boxes-helpers';

// TC-NEW-PRINT-01 — этикетка 58×40: превью (EAC, артикул, название), диалог количества.
test('ff inbound modal opens 58x40 label print dialog with preview', async ({ page }) => {
  const suffix = String(Date.now());
  const adminEmail = `ff-lbl-${suffix}@example.com`;
  const password = 'password123';
  const sku = `SKU-LBL-${suffix}`;
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Label');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: h,
    data: JSON.stringify({ name: `Lbl Seller ${suffix}` }),
  });
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);
  await page.request.patch(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: h,
    data: JSON.stringify({ content_api_token: 'e2e-content', supplies_api_token: 'e2e-supplies' }),
  });
  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: h,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId }),
  });
  const jobId = String(((await jobRes.json()) as { id: string }).id);
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, { headers: h });
      return (await jr.json()) as { status: string };
    })
    .toMatchObject({ status: 'done' });

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: h,
    data: JSON.stringify({ name: 'WH', code: `wh-lbl-${suffix}` }),
  });
  const warehouseId = String(((await whRes.json()) as { id: string }).id);

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: h,
    data: JSON.stringify({
      name: 'Брюки коричневые L',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);
  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: h,
    data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
  });

  const cr = await page.request.post(INBOUND_API, {
    headers: h,
    data: { warehouse_id: warehouseId },
  });
  expect(cr.ok()).toBeTruthy();
  const rid = String(((await cr.json()) as { id: string }).id);
  await page.request.post(`${INBOUND_API}/${rid}/lines`, {
    headers: h,
    data: { product_id: productId, expected_qty: 2 },
  });
  await page.request.post(`${INBOUND_API}/${rid}/submit`, { headers: h });

  await loginFfAdmin(page, adminEmail, password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();

  const table = page.getByTestId('ff-inbound-lines-table');
  await expect(table.getByRole('columnheader', { name: 'Фото' })).toBeVisible();
  await expect(table.getByRole('columnheader', { name: 'ШК' })).toBeVisible();

  await table.getByRole('button', { name: 'Печать ШК товара' }).first().click();
  const dialog = page.getByTestId('ff-product-label-print-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Печать этикетки 58×40')).toBeVisible();
  await expect(page.getByTestId('ff-product-label-preview')).toContainText('Брюки коричневые');
  await expect(page.getByTestId('ff-product-label-preview')).toContainText('Производитель: Россия');
  await expect(page.getByTestId('ff-product-label-preview')).toContainText('Артикул:');
  await expect(page.getByTestId('ff-product-label-preview')).toContainText('E2E-MOCK-BARCODE');
  await expect(page.getByTestId('ff-product-label-print')).toBeEnabled();

  await page.getByTestId('ff-product-label-qty').fill('3');
  await page.getByTestId('ff-product-label-print').click();
  await expect(dialog).not.toBeVisible();
});
