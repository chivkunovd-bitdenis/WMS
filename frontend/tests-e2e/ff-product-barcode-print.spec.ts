import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { INBOUND_API, loginFfAdmin } from './inbound-boxes-helpers';

// TC-NEW-PRINT-01 — единый диалог печати (MarkingPrintDialog) в сортировке после приёмки.
test('ff sorting opens unified marking print dialog for product line', async ({ page }) => {
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
  await page.request.post(`/api/warehouses/${warehouseId}/locations`, {
    headers: h,
    data: JSON.stringify({ code: 'STORE-1' }),
  });

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

  const barcode = 'E2E-MOCK-BARCODE';
  for (let i = 0; i < 2; i++) {
    const scanRes = await page.request.post(`${INBOUND_API}/${rid}/receiving/scan`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: JSON.stringify({ barcode }),
    });
    expect(scanRes.ok()).toBeTruthy();
  }
  const completeRes = await page.request.post(`${INBOUND_API}/${rid}/complete-receiving`, { headers: h });
  expect(completeRes.ok()).toBeTruthy();

  await loginFfAdmin(page, adminEmail, password);
  await page.goto('/app/ff/sorting');
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1, { timeout: 20000 });
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible();

  const linesTable = page.getByTestId('ff-inbound-lines-table');
  await expect(linesTable).toBeVisible();
  await expect(linesTable.getByRole('button', { name: 'Печать ШК товара' })).toHaveCount(0);

  const productCard = page.getByTestId('ff-sorting-product-card').first();
  await productCard.getByRole('button', { name: 'Печать ШК товара' }).click();
  const dialog = page.getByTestId('marking-print-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Брюки коричневые');
  await expect(page.getByTestId('marking-print-wb-qty')).toBeVisible();
  await expect(page.getByTestId('marking-print-qty')).toContainText('К упаковке: 2');
  await page.getByTestId('marking-print-wb-qty').locator('input').fill('3');
  await expect(page.getByTestId('marking-print-will-print')).toContainText('К печати: 6 ШК ВБ');
  await page.getByTestId('marking-print-confirm').click();
  await expect(dialog).toBeHidden();

  const barcodeCell = productCard.getByTestId('ff-product-line-barcode');
  await expect(barcodeCell).toContainText('E2E-MOCK-BARCODE');
  await expect(barcodeCell).toContainText('Размер: L');
  await expect(barcodeCell).toContainText('Состав:');
});
