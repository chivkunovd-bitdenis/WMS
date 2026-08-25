import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { beginInboundReceivingWithBoxes, fulfillInboundViaBoxScans } from './inbound-boxes-helpers';
import { openFulfillmentRegistration } from './auth-flow';

function formatDisplayDocumentNumber(documentNumber: string): string {
  const counter = documentNumber.match(/(\d+)\s*$/)?.[1];
  expect(counter).toBeTruthy();
  return `№${counter!.padStart(6, '0')}`;
}

function visiblePackagingNumber(task: {
  display_number?: string | null;
  public_number?: string | null;
  human_number?: string | null;
  document_number?: string | null;
}): string | null {
  const preferred = task.display_number ?? task.public_number ?? task.human_number;
  if (preferred && preferred.trim()) {
    return preferred.trim();
  }
  if (!task.document_number) {
    return null;
  }
  return formatDisplayDocumentNumber(task.document_number);
}

// TC-NEW-PKG-01 — FF создаёт задание из сортировки и упаковывает через UI.
test('FF packaging page: create from sorting and pack line', async ({ page }) => {
  test.setTimeout(120_000);
  const email = `e2e-pkg-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`;
  const sku = `SKU-PKG-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Packaging');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-pkg-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Pack Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 4 }),
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
    sku,
    [4],
  );
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  await page.goto('/app/ff/packaging');
  await expect(page.getByTestId('ff-packaging-page')).toBeVisible();
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy();

  await page.getByTestId('ff-packaging-create-open').click();
  await expect(page.getByTestId('ff-packaging-create-dialog')).toBeVisible();
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy();
  await page.getByTestId('ff-packaging-create-warehouse').click();
  await page.getByRole('option', { name: 'WH' }).click();
  await page.getByTestId('ff-packaging-create-location').click();
  await page.getByRole('option', { name: 'Сортировка' }).click();
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible();
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy();
  await expect(page.getByTestId('ff-packaging-create-summary')).toContainText('0 селлеров');
  await expect(page.getByTestId('ff-packaging-create-submit')).toBeDisabled();
  await page.locator('[data-testid^="ff-packaging-create-row-select-"]').first().click();
  await expect(page.getByTestId('ff-packaging-create-summary')).toContainText('1 селлер');
  await page.getByTestId(`ff-packaging-create-qty-${productId}`).fill('1.5');
  await expect(page.getByTestId('ff-packaging-create-submit')).toBeDisabled();
  await expect(page.getByText('Введите целое число')).toBeVisible();
  await page.getByTestId(`ff-packaging-create-qty-${productId}`).fill('4');
  await expect(page.getByTestId('ff-packaging-create-submit')).toBeEnabled();

  const createResponsePromise = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/packaging-tasks') &&
      r.status() >= 200 &&
      r.status() < 300,
  );
  await page.getByTestId('ff-packaging-create-submit').click();
  const createResponse = await createResponsePromise;
  const createdTask = (await createResponse.json()) as {
    document_number: string | null;
    display_number?: string | null;
    public_number?: string | null;
    human_number?: string | null;
  };
  const packagingDisplayNumber = visiblePackagingNumber(createdTask);
  expect(packagingDisplayNumber).toBeTruthy();

  // TC-NEW-DOCNUM-01 — human-readable packaging document number on create.
  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible();
  await expect(page.getByTestId('ff-packaging-document-number')).toHaveText(packagingDisplayNumber);
  await expect(page.getByTestId('ff-packaging-service-id')).toHaveCount(0);
  await expect(page.getByTestId('ff-packaging-line')).toBeVisible();
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy();

  await page.getByTestId('ff-packaging-scanner-input').fill(sku);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/scan') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-line')).toContainText('Готово 1 / Осталось 3 / Всего 4');

  await page.getByTestId('ff-packaging-scanner-input').fill(`${sku}-UNKNOWN`);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/scan') &&
        r.status() === 409,
    ),
    page.getByTestId('ff-packaging-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-error')).toContainText('ШК не найден в этом задании');
  await expect(page.getByTestId('ff-packaging-error')).not.toContainText('unknown_barcode');
  await expect(page.getByTestId('ff-packaging-line')).toContainText('Готово 1 / Осталось 3 / Всего 4');

  await page.locator('[data-testid^="ff-packaging-manual-qty-"]').first().fill('2');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/lines/') &&
        r.url().includes('/pack') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-pack-btn').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-line')).toContainText('Готово 3 / Осталось 1 / Всего 4');

  await page.getByTestId('ff-packaging-undo-last').click();
  await expect(page.getByTestId('ff-packaging-undo-confirm-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-packaging-undo-confirm-message')).toContainText('2 шт');
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/undo-last') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-undo-confirm-submit').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-undo-confirm-dialog')).toBeHidden();
  await expect(page.getByTestId('ff-packaging-line')).toContainText('Готово 1 / Осталось 3 / Всего 4');

  for (let idx = 0; idx < 3; idx += 1) {
    await page.getByTestId('ff-packaging-scanner-input').fill(sku);
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.request().method() === 'POST' &&
          r.url().includes('/scan') &&
          r.status() >= 200 &&
          r.status() < 300,
      ),
      page.getByTestId('ff-packaging-scan-submit').click(),
    ]);
  }
  await expect(page.getByTestId('ff-packaging-line')).toContainText('Готово 4 / Осталось 0 / Всего 4');

  await page.getByTestId('ff-packaging-scanner-input').fill(sku);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/scan') &&
        r.status() === 409,
    ),
    page.getByTestId('ff-packaging-scan-submit').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-error')).toContainText('По этому товару всё уже упаковано');
  await expect(page.getByTestId('ff-packaging-error')).not.toContainText('line_already_packed');

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/complete') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-complete').click(),
  ]);

  await expect(page.getByTestId('ff-packaging-task-status')).toContainText('Выполнено');
});

// TC-NEW-PKG-05 — FF создаёт задание из ячейки (не сортировка).
test('FF packaging page: create from storage cell', async ({ page }) => {
  test.setTimeout(120_000);
  const email = `e2e-pkg-cell-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`;
  const sku = `SKU-CELL-${Date.now()}`;
  const locCode = `A-${Date.now().toString().slice(-4)}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Packaging Cell');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-cell-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);
  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: locCode }),
  });
  const locId = String(((await locRes.json()) as { id: string }).id);

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Cell Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  const lineRes = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 3 }),
  });
  const lineId = String(((await lineRes.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  );
  await page.request.patch(`${baseIn}/${inboundId}/lines/${lineId}`, {
    headers: auth,
    data: JSON.stringify({ storage_location_id: locId }),
  });
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, sku, [3]);
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  await page.goto('/app/ff/packaging');
  await page.getByTestId('ff-packaging-create-open').click();
  await page.getByTestId('ff-packaging-create-warehouse').click();
  await page.getByRole('option', { name: 'WH' }).click();
  await page.getByTestId('ff-packaging-create-location').click();
  await page.getByRole('option', { name: locCode }).click();
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible();
  await page.locator('[data-testid^="ff-packaging-create-row-select-"]').first().click();

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/packaging-tasks') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-create-submit').click(),
  ]);

  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible();
  await expect(page.getByTestId('ff-packaging-line')).toBeVisible();
});

// TC-NEW-PKG-06 — FF отменяет ручное задание на упаковку.
test('FF packaging page: cancel manual task', async ({ page }) => {
  test.setTimeout(120_000);
  const email = `e2e-pkg-cancel-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`;
  const sku = `SKU-CAN-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Packaging Cancel');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-can-${Date.now()}` }),
  });
  const whId = String(((await whRes.json()) as { id: string }).id);
  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Cancel Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
    }),
  });
  const productId = String(((await prRes.json()) as { id: string }).id);

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`;
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  });
  const inboundId = String(((await inbound.json()) as { id: string }).id);
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 2 }),
  });
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth });
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  );
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, sku, [2]);
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth });
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth });

  await page.goto('/app/ff/packaging');
  await page.getByTestId('ff-packaging-create-open').click();
  await page.getByTestId('ff-packaging-create-warehouse').click();
  await page.getByRole('option', { name: 'WH' }).click();
  await page.getByTestId('ff-packaging-create-location').click();
  await page.getByRole('option', { name: 'Сортировка' }).click();
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible();
  await page.locator('[data-testid^="ff-packaging-create-row-select-"]').first().click();

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/packaging-tasks') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-create-submit').click(),
  ]);

  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/cancel') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-cancel-task').click(),
  ]);
  await expect(page.getByTestId('ff-packaging-queue')).toBeVisible();
});
