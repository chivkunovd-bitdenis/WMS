import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
} from './inbound-boxes-helpers';

// TC-NEW-TZ-PRINT-01 — кнопка «Печать ТЗ» в отгрузке на МП: сводная A4-форма со всеми товарами и их ТЗ.
// Given: отгрузка на МП с товаром, у которого заполнено ТЗ на упаковку.
// When: оператор на вкладке «Товары» жмёт «Печать ТЗ».
// Then: формируется печатная форма, где напротив товара — его ТЗ из карточки; пустое ТЗ → плейсхолдер.
test('FF marketplace unload: Печать ТЗ builds packaging sheet with per-product instructions', async ({
  page,
}) => {
  const suffix = String(Date.now());
  const email = `e2e-mp-tz-${suffix}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP TZ');
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
    data: JSON.stringify({ name: 'W', code: `w-tz-${suffix}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'TZ Seller' }),
  });
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  await page.request.patch(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: auth,
    data: JSON.stringify({ content_api_token: 'e2e-content', supplies_api_token: 'e2e-supplies' }),
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

  // Товар с ТЗ.
  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Носки хлопок',
      sku_code: `tz-sku-${suffix}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E: сложить в пакет и наклеить стикер WB' }),
  });

  // Остаток на складе нужен, чтобы товар можно было добавить в отгрузку.
  const barcode = 'E2E-MOCK-BARCODE';
  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'TZ-LOC' }),
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
    data: JSON.stringify({ product_id: productId, expected_qty: 5, storage_location_id: locId }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  );
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, barcode, [5]);
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, { headers: auth });
  const wbWid = Number(((await whs.json()) as { wb_warehouse_id: number }[])[0].wb_warehouse_id);

  const mu = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId, seller_id: sellerId, wb_mp_warehouse_id: wbWid }),
  });
  const mid = String(((await mu.json()) as { id: string }).id);
  const lineRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`,
    { headers: auth, data: JSON.stringify({ product_id: productId, quantity: 2 }) },
  );
  expect(lineRes.ok()).toBeTruthy();

  await page.reload();
  await page.getByTestId('nav-ff-mp-shipments').click();
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible();
  await Promise.all([
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ]);
  const docDialog = page.getByTestId('ff-supplies-doc-dialog');
  await expect(docDialog).toBeVisible();
  // Дождаться загрузки состава отгрузки (товар в списке).
  await expect(docDialog).toContainText('Носки хлопок', { timeout: 15000 });
  // Каталог (ТЗ/фото/артикулы) подтягивается после загрузки отгрузки — ждём артикул WB в строке.
  await expect(docDialog).toContainText('424242', { timeout: 15000 });

  const printActions = page.getByTestId('ff-mp-print-actions');
  await printActions.scrollIntoViewIfNeeded();
  await expect(printActions).toBeVisible({ timeout: 15000 });
  await expect(printActions.getByTestId('ff-mp-print-tz')).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { __WMS_CAPTURE_PRINT_HTML__?: boolean }).__WMS_CAPTURE_PRINT_HTML__ = true;
  });
  await page.getByTestId('ff-mp-print-tz').click();

  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ ?? '',
      ),
    )
    .toContain('data-testid="tz-sheet-card"');

  const html = await page.evaluate(
    () => (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ ?? '',
  );
  expect(html).toContain('ТЗ на упаковку');
  expect(html).toContain('E2E: сложить в пакет и наклеить стикер WB');
  expect(html).toContain('Носки хлопок');
  expect(html).toContain('size: A4');
  expect(html).not.toContain('size: A4 portrait');
  expect(html).toContain('data-testid="tz-sheet-qty"');
  expect(html).toContain('>2</span>');
});
