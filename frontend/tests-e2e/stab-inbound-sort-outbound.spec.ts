import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

const MP_BARCODE = 'E2E-MOCK-BARCODE';
const EXPECTED_QTY = 4;
const BOX2_QTY = 2;
const LOOSE_QTY = 2;
const UNLOAD_QTY = 2;

/** TC-NEW-STAB-E2E-01 — STAB-E2E-01: приёмка → сортировка видна → отгрузка из буфера без раскладки. */
test('stab inbound sort outbound — receive, see sorting, ship from buffer without distribution', async ({
  page,
}) => {
  test.setTimeout(180_000);

  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const seed = await seedFfSellerInbound(page, `stab-e2e-${Date.now()}`);
  await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 0,
    expectedQty: EXPECTED_QTY,
  });

  const auth = {
    Authorization: `Bearer ${seed.token}`,
    'Content-Type': 'application/json',
  };

  await page.request.patch(
    `${e2eApi}/integrations/wildberries/sellers/${seed.sellerId}/tokens`,
    {
      headers: auth,
      data: JSON.stringify({
        content_api_token: 'e2e-content',
        supplies_api_token: 'e2e-supplies',
      }),
    },
  );

  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: auth,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: seed.sellerId }),
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

  await page.request.post(
    `${e2eApi}/integrations/wildberries/sellers/${seed.sellerId}/link-product`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: seed.productId, nm_id: 424242 }),
    },
  );

  await page.request.patch(`${e2eApi}/products/${seed.productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ packaging_instructions: 'STAB-E2E: пакет' }),
  });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-receiving-scan-panel')).toBeVisible();

  for (let i = 0; i < 2; i++) {
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.endsWith('/boxes')),
      page.getByTestId('ff-inbound-add-to-box').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  }
  await expect(page.getByTestId('ff-inbound-box-open')).toHaveCount(2);

  await page.getByTestId('ff-inbound-box-open').nth(1).getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-box-label')).toContainText('Короб № 2');
  for (let i = 0; i < BOX2_QTY; i++) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ]);
  }
  await expect(page.getByTestId('ff-inbound-box-add-qty')).toHaveText(String(BOX2_QTY));
  await page.getByTestId('ff-inbound-box-add-close').click();
  await expect(page.getByTestId('ff-inbound-box-open').nth(1)).toContainText(seed.sku);

  for (let i = 0; i < LOOSE_QTY; i++) {
    await page.getByTestId('ff-inbound-receiving-scan-input').fill(seed.sku);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/receiving/scan')),
      page.getByTestId('ff-inbound-receiving-scan-submit').click(),
    ]);
  }
  await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText(
    String(EXPECTED_QTY),
  );
  await expect(page.getByTestId('ff-inbound-verify-complete')).toBeEnabled();

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');

  await page.getByTestId('ff-doc-dialog-close').click();
  await Promise.all([
    waitForGetOk(page, INBOUND_API),
    page.goto('/app/ff/sorting'),
  ]);
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(page.getByTestId('ff-inbound-queue-sorting-qty').first()).toHaveText(
    String(EXPECTED_QTY),
  );

  const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, { headers: auth });
  const wbWid = Number(((await whs.json()) as { wb_warehouse_id: number }[])[0].wb_warehouse_id);

  const mu = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({
      warehouse_id: seed.warehouseId,
      seller_id: seed.sellerId,
      wb_mp_warehouse_id: wbWid,
    }),
  });
  const mid = String(((await mu.json()) as { id: string }).id);
  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: seed.productId, quantity: UNLOAD_QTY }),
  });
  const confirmRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`,
    {
      headers: auth,
      data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
    },
  );
  expect(confirmRes.ok()).toBeTruthy();

  await page.reload();
  await page.getByTestId('nav-ff-mp-shipments').click();
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ]);
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible();

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ]);

  const addBtn = page.locator('[data-testid^="ff-mp-box-add-products-"]');
  const addTestId = await addBtn.getAttribute('data-testid');
  const boxId = addTestId?.replace('ff-mp-box-add-products-', '') ?? '';
  await addBtn.click();
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-mp-box-add-sorting-buffer-hint')).toBeVisible();
  await expect(page.getByTestId(`ff-mp-box-add-available-${seed.productId}`)).toHaveText(
    String(UNLOAD_QTY),
  );

  await page.getByTestId('ff-mp-box-add-scan-input').fill(MP_BARCODE);
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${mid}/boxes/${boxId}/scan`,
    ),
    page.getByTestId('ff-mp-box-add-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-mp-box-add-success-snackbar')).toContainText('Добавлено 1 шт');
  await expect(page.getByTestId('ff-mp-open-box-lines')).toContainText('1');
  await expect(page.getByText(/недостаточно доступного остатка в выбранной ячейке/i)).toHaveCount(0);
});
