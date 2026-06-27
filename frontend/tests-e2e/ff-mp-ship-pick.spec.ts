import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers';

// TC-NEW-MP-01 / TASK-017 — упаковка → короб → скан → ship; остаток списывается при collect, не при ship.
test('FF marketplace unload: pick by cell and ship reduces stock', async ({ page }) => {
  const email = `e2e-mp-ship-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const barcode = 'E2E-MOCK-BARCODE';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Ship');
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

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'W', code: `w-mp-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'MP Seller' }),
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

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'MP Product',
      sku_code: `mp-sku-${Date.now()}`,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerId,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);

  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
  });

  await page.request.patch(`${e2eApi}/products/${productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ packaging_instructions: 'E2E: пакет + стикер WB' }),
  });

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'MP-LOC' }),
  });
  const locId = String(((await locRes.json()) as { id: string }).id);

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 5,
      storage_location_id: locId,
    }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const primIn = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  });
  const primInBody = (await primIn.json()) as {
    boxes: { id: string; internal_barcode: string }[];
  };
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    primInBody.boxes,
    barcode,
    [5],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 5 }),
  });
  await page.request.post(`${baseIn}/${sortInboundId}/submit`, { headers: auth });
  const primSort = await page.request.post(`${baseIn}/${sortInboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  });
  const primSortBody = (await primSort.json()) as {
    boxes: { id: string; internal_barcode: string }[];
  };
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    sortInboundId,
    primSortBody.boxes,
    barcode,
    [5],
  );
  await page.request.post(`${baseIn}/${sortInboundId}/verify`, { headers: auth });

  const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, { headers: auth });
  const wbWid = Number(((await whs.json()) as { wb_warehouse_id: number }[])[0].wb_warehouse_id);

  const mu = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({
      warehouse_id: whId,
      seller_id: sellerId,
      wb_mp_warehouse_id: wbWid,
    }),
  });
  const mid = String(((await mu.json()) as { id: string }).id);
  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, quantity: 3 }),
  });

  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`, {
    headers: auth,
    data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
  });

  const pkgBeforeBox = await page.request.get(
    `${e2eApi}/operations/packaging-tasks/by-unload/${mid}`,
    { headers: auth },
  );
  expect(pkgBeforeBox.ok()).toBeTruthy();
  const pkgBeforeBody = (await pkgBeforeBox.json()) as {
    id: string;
    lines: { id: string; qty_need_pack: number }[];
  };
  const pkgLineBefore = pkgBeforeBody.lines[0];
  expect(pkgLineBefore?.id).toBeTruthy();
  if (pkgLineBefore && pkgLineBefore.qty_need_pack > 0) {
    await page.request.post(
      `${e2eApi}/operations/packaging-tasks/${pkgBeforeBody.id}/lines/${pkgLineBefore.id}/pack`,
      {
        headers: auth,
        data: JSON.stringify({ quantity: pkgLineBefore.qty_need_pack }),
      },
    );
  }
  const pkgComplete = await page.request.post(
    `${e2eApi}/operations/packaging-tasks/${pkgBeforeBody.id}/complete`,
    { headers: auth, data: JSON.stringify({ acknowledge_all_packed: false }) },
  );
  expect(pkgComplete.ok()).toBeTruthy();

  const box = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/boxes`,
    { headers: auth, data: JSON.stringify({ box_preset: '60_40_40' }) },
  );
  expect(box.ok()).toBeTruthy();
  const boxId = String(((await box.json()) as { id: string }).id);

  const locList = await page.request.get(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
  });
  const locBarcode = String(
    ((await locList.json()) as { id: string; barcode: string }[]).find((x) => x.id === locId)
      ?.barcode,
  );

  const locScan = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/pick/scan`,
    { headers: auth, data: JSON.stringify({ barcode: locBarcode }) },
  );
  expect(locScan.ok()).toBeTruthy();

  for (let i = 0; i < 3; i += 1) {
    const prodScan = await page.request.post(
      `${e2eApi}/operations/marketplace-unload-requests/${mid}/boxes/${boxId}/scan`,
      {
        headers: auth,
        data: JSON.stringify({ barcode, storage_location_id: locId }),
      },
    );
    expect(prodScan.ok()).toBeTruthy();
  }

  const detail = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}`,
    { headers: auth },
  );
  expect(((await detail.json()) as { lines: { picked_qty: number }[] }).lines[0].picked_qty).toBe(
    3,
  );

  const balAfterCollect = await page.request.get(
    `${e2eApi}/operations/inventory-balances/summary`,
    { headers: auth, params: { warehouse_id: whId } },
  );
  const rowAfterCollect = (
    (await balAfterCollect.json()) as { product_id: string; quantity: number }[]
  ).find((x) => x.product_id === productId);
  expect(rowAfterCollect?.quantity).toBe(7);

  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/ship`, {
    headers: auth,
  });

  const bal = await page.request.get(`${e2eApi}/operations/inventory-balances/summary`, {
    headers: auth,
    params: { warehouse_id: whId },
  });
  const row = ((await bal.json()) as { product_id: string; quantity: number }[]).find(
    (x) => x.product_id === productId,
  );
  expect(row?.quantity).toBe(7);

  await page.reload();
  await page.getByTestId('nav-ff-mp-shipments').click();
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible();
  await Promise.all([
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Отгружено');
});
