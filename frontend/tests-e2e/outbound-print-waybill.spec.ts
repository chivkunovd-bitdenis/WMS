import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import {beginInboundReceivingWithBoxes,  fulfillInboundViaBoxScans } from './inbound-boxes-helpers';

// TC-NEW-G13-002 — накладная operational outbound (US-G-13).
test('FF prints operational outbound waybill from ops screen', async ({ page }) => {
  const email = `e2e-obw-${Date.now()}@example.com`;
  const sku = `SKU-OBW-${Date.now()}`;
  const whCode = `wh-obw-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E OB Waybill');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const regClick = page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click();
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    regClick,
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const wh = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: whCode }),
  });
  const wid = String(((await wh.json()) as { id: string }).id);
  const loc = await page.request.post(`${e2eApi}/warehouses/${wid}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'OBW-A' }),
  });
  const lid = String(((await loc.json()) as { id: string }).id);
  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'OBW Brand' }),
  });
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);
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
      name: 'T',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  });
  const pid = String(((await pr.json()) as { id: string }).id);
  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: JSON.stringify({ product_id: pid, nm_id: 424242 }),
  });

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: wid }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: pid,
      expected_qty: 10,
      storage_location_id: lid,
    }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  );
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    inboundBoxes,
    'E2E-MOCK-BARCODE',
    [10],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  await page.goto('/app/ops/outbound');
  await Promise.all([
    waitForPostOk(page, '/api/operations/outbound-shipment-requests', (u) =>
      !u.includes('/lines') && !u.includes('/submit'),
    ),
    page.getByTestId('outbound-create-submit').click(),
  ]);
  await page.getByTestId('outbound-line-product').selectOption({ label: `${sku} — T` });
  await page.getByTestId('outbound-line-qty').fill('3');
  await page.getByTestId('outbound-line-location').selectOption({ label: 'OBW-A' });
  await Promise.all([
    waitForPostOk(page, '/api/operations/outbound-shipment-requests', (u) => u.includes('/lines')),
    page.getByTestId('outbound-line-submit').click(),
  ]);

  await page.getByTestId('outbound-request-item').first().click();
  await expect(page.getByTestId('outbound-detail-lines')).toContainText(sku);
  const printBtn = page.getByTestId('outbound-print-waybill');
  await expect(printBtn).toBeVisible();
  await printBtn.click();
});
