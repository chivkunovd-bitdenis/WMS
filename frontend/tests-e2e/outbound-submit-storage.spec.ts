import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForPostOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers';

// TC-NEW-13-001 — submit outbound blocked until every line has a storage cell.
test('outbound submit disabled without storage; succeeds after assigning cell', async ({
  page,
}) => {
  test.setTimeout(120_000);
  const email = `e2e-oss-${Date.now()}@example.com`;
  const sku = `SKU-OSS-${Date.now()}`;
  const whCode = `wh-oss-${Date.now()}`;
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E OSS');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
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
    data: JSON.stringify({ code: 'OSS-A' }),
  });
  const lid = String(((await loc.json()) as { id: string }).id);
  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'OSS Brand' }),
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
  const prim = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  });
  const boxes = (await prim.json()) as {
    boxes: { id: string; internal_barcode: string }[];
  };
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    boxes.boxes,
    'E2E-MOCK-BARCODE',
    [10],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  const baseOut = `${e2eApi}/operations/outbound-shipment-requests`;
  const out = await page.request.post(baseOut, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: wid }),
  });
  const oid = String(((await out.json()) as { id: string }).id);
  const line = await page.request.post(`${baseOut}/${oid}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: pid, quantity: 4 }),
  });
  expect(line.ok()).toBeTruthy();
  const lineId = String(((await line.json()) as { id: string }).id);

  const badSubmit = await page.request.post(`${baseOut}/${oid}/submit`, { headers: auth });
  expect(badSubmit.status()).toBe(422);
  expect(((await badSubmit.json()) as { detail: string }).detail).toBe(
    'lines_missing_storage',
  );

  await page.goto('/app/ops/outbound');
  await page.getByTestId('outbound-request-item').first().click();
  await expect(page.getByTestId('outbound-detail-status')).toContainText('draft');
  await expect(page.getByTestId('outbound-submit-missing-storage-hint')).toBeVisible();
  await expect(page.getByTestId('outbound-submit-request')).toBeDisabled();

  const storageForm = page.locator(
    `[data-testid="outbound-line-storage-form"][data-line-id="${lineId}"]`,
  );
  await storageForm.getByTestId('outbound-line-storage-select').selectOption({ label: 'OSS-A' });
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/operations/outbound-shipment-requests/${oid}/lines/`) &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    storageForm.getByTestId('outbound-line-storage-save').click(),
  ]);

  await expect(page.getByTestId('outbound-submit-request')).toBeEnabled();
  await Promise.all([
    waitForPostOk(page, '/api/operations/outbound-shipment-requests', (u) =>
      u.includes('/submit'),
    ),
    page.getByTestId('outbound-submit-request').click(),
  ]);
  await expect(page.getByTestId('outbound-detail-status')).toContainText('submitted');
});
