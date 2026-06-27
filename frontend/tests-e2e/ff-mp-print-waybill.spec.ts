import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers';

// TC-NEW-G13-001 — печать накладной отгрузки на МП (US-G-13).
test('FF prints marketplace unload waybill from document dialog', async ({ page }) => {
  const email = `e2e-wb-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const sku = `SKU-WB-${Date.now()}`;
  const barcode = 'E2E-MOCK-BARCODE';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Waybill');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'));
  expect(token).toBeTruthy();
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const wh = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-wb-${Date.now()}` }),
  });
  const wid = String(((await wh.json()) as { id: string }).id);
  const loc = await page.request.post(`${e2eApi}/warehouses/${wid}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'WB-LOC' }),
  });
  const lid = String(((await loc.json()) as { id: string }).id);

  const seller = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'WB Seller' }),
  });
  const sellerId = String(((await seller.json()) as { id: string }).id);
  await page.request.patch(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: auth,
    data: JSON.stringify({
      content_api_token: 'e2e-content',
      supplies_api_token: 'e2e-supplies',
    }),
  });
  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: auth,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId }),
  });
  const jobId = String(((await jobRes.json()) as { id: string }).id);
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, {
        headers: auth,
      });
      return (await jr.json()) as { status: string };
    })
    .toMatchObject({ status: 'done' });

  const pr = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'P',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  });
  const pid = String(((await pr.json()) as { id: string }).id);
  await page.request.post(
    `${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: pid, nm_id: 424242 }),
    },
  );

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: wid }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: pid, expected_qty: 5, storage_location_id: lid }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const prim = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  });
  const boxes = (await prim.json()) as { boxes: { id: string; internal_barcode: string }[] };
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, boxes.boxes, barcode, [5]);
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  const mp = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: wid, seller_id: sellerId }),
  });
  const mid = String(((await mp.json()) as { id: string }).id);
  const linesRes = await page.request.put(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`,
    {
      headers: auth,
      data: JSON.stringify({ lines: [{ product_id: pid, quantity: 2 }] }),
    },
  );
  expect(linesRes.ok()).toBeTruthy();

  await page.goto('/app/ff/mp-shipments');
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible();
  await expect(page.getByTestId('ff-docs-row').first()).toBeVisible();
  await page.getByTestId('ff-docs-row').first().click();
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-supplies-doc-lines')).toContainText(sku);
  await page.getByTestId('ff-mp-tab-final').click();
  await expect(page.getByTestId('ff-mp-tab-final-panel')).toBeVisible();
  const printBtn = page.getByTestId('ff-mp-print-waybill');
  await expect(printBtn).toBeVisible();
  await expect(printBtn).toBeEnabled();
  await printBtn.click();
});
