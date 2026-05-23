import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-NEW-C02 — подсказки ячеек при распределении: где уже лежит товар.
test('ff inbound distribution shows cell hints from existing stock', async ({ page }) => {
  const email = `e2e-hint-${Date.now()}@example.com`;
  const sku = `SKU-HINT-${Date.now()}`;
  const whCode = `wh-hint-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Hints');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  const wid = ((await wh.json()) as { id: string }).id;

  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'CELL-A' },
  });
  const lid = ((await loc.json()) as { id: string }).id;

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';

  async function postInbound(qty: number) {
    const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
    const rid = ((await cr.json()) as { id: string }).id;
    await page.request.post(`${base}/${rid}/lines`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { product_id: pid, expected_qty: qty },
    });
    await page.request.post(`${base}/${rid}/submit`, { headers: h });
    const prim = await page.request.post(`${base}/${rid}/primary-accept`, {
      headers: h,
      data: { actual_box_count: 1 },
    });
    const inb = ((await prim.json()) as { boxes: { internal_barcode: string }[] }).boxes[0]!
      .internal_barcode;
    await page.request.post(`${base}/${rid}/boxes/open`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { barcode: inb },
    });
    const detail = await page.request.get(`${base}/${rid}`, { headers: h });
    const boxId = ((await detail.json()) as { boxes: { id: string }[] }).boxes[0]!.id;
    for (let n = 0; n < qty; n++) {
      await page.request.post(`${base}/${rid}/boxes/${boxId}/scan`, {
        headers: { ...h, 'Content-Type': 'application/json' },
        data: { barcode: sku },
      });
    }
    await page.request.post(`${base}/${rid}/boxes/${boxId}/close`, { headers: h });
    await page.request.post(`${base}/${rid}/verify`, { headers: h });
    await page.request.put(`${base}/${rid}/distribution-lines`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: [{ product_id: pid, storage_location_id: lid, quantity: qty }],
    });
    await page.request.post(`${base}/${rid}/distribution-complete`, { headers: h });
    return rid;
  }

  await postInbound(3);

  const cr2 = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid2 = ((await cr2.json()) as { id: string }).id;
  const planned = new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  await page.request.patch(`${base}/${rid2}`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { planned_delivery_date: planned },
  });
  await page.request.post(`${base}/${rid2}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 2 },
  });
  await page.request.post(`${base}/${rid2}/submit`, { headers: h });
  const prim2 = await page.request.post(`${base}/${rid2}/primary-accept`, {
    headers: h,
    data: { actual_box_count: 1 },
  });
  const inb2 = ((await prim2.json()) as { boxes: { internal_barcode: string }[] }).boxes[0]!
    .internal_barcode;

  await page.goto('/app/ff/dashboard');
  await page.getByTestId('ff-dash-inbound-row').filter({ hasText: planned }).first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();

  await page.getByTestId('ff-inbound-box-open-scan').fill(inb2);
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/boxes/open')),
    page.getByTestId('ff-inbound-box-open-submit').click(),
  ]);
  for (let n = 0; n < 2; n++) {
    await page.getByTestId('ff-inbound-product-scan').fill(sku);
    await Promise.all([
      waitForPostOk(page, base, (u) => u.includes('/scan')),
      page.getByTestId('ff-inbound-product-scan-submit').click(),
    ]);
  }
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/close')),
    page.getByTestId('ff-inbound-box-close').click(),
  ]);
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/verify')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);

  await page.getByTestId('ff-inbound-distribute-open').click();
  await page.getByTestId('ff-inbound-distribution-add-row').click();
  const row = page.getByTestId('ff-inbound-distribution-row').first();
  await row.getByTestId('ff-inbound-distribution-product').click();
  await page.getByRole('option', { name: new RegExp(sku) }).click();

  const hints = page.getByTestId('ff-inbound-cell-hints');
  await expect(hints).toBeVisible();
  const hint = page.getByTestId('ff-inbound-cell-hint').filter({ hasText: 'CELL-A' });
  await expect(hint).toContainText('(3)');
  await hint.click();
  await expect(row.getByTestId('ff-inbound-distribution-location')).toContainText('CELL-A');
});
