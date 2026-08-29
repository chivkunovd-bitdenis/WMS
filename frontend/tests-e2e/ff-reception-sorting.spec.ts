import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { expandInboundPackages } from './inbound-boxes-helpers';

// TC-NEW-FF-INBOUND-001 — ФФ создаёт черновик приёмки из очереди приёмки и сразу открывает документ.
test('ff reception can create inbound draft and open it', async ({ page }) => {
  const email = `e2e-ff-inb-${Date.now()}@example.com`;
  const whCode = `wh-ff-inb-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Inbound');
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
    data: { name: 'Склад ФФ', code: whCode },
  });
  expect(wh.ok()).toBeTruthy();
  const seller = await page.request.post('/api/sellers', {
    headers: h,
    data: { name: 'REC-12 Seller' },
  });
  expect(seller.ok()).toBeTruthy();
  const sellerId = String(((await seller.json()) as { id: string }).id);

  await page.goto('/app/ff/reception');
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Приёмка на FF' })).toBeVisible();
  await expect(page.getByTestId('ff-inbound-create')).toBeEnabled();
  await expect(page.getByTestId('ff-inbound-new-count')).toContainText('Новые приёмки: 0');

  await page.getByTestId('ff-inbound-create').click();
  await expect(page.getByTestId('ff-inbound-create-dialog')).toBeVisible();
  await page.getByTestId('ff-inbound-create-seller').click();
  await page.getByRole('option', { name: 'REC-12 Seller' }).click();

  const [createRes] = await Promise.all([
    waitForPostOk(
      page,
      '/api/operations/inbound-intake-requests',
      (u) => !u.includes('/lines') && !u.includes('/submit'),
    ),
    page.getByTestId('ff-inbound-create-confirm').click(),
  ]);
  expect(createRes.ok()).toBeTruthy();
  const createBody = JSON.parse(createRes.request().postData() ?? '{}') as { seller_id?: string };
  expect(createBody.seller_id).toBe(sellerId);
  const created = (await createRes.json()) as { id: string; status: string; seller_id: string };
  expect(created.status).toBe('draft');
  expect(created.seller_id).toBe(sellerId);

  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Черновик');
  await expect(page.getByTestId('ff-inbound-add-products')).toBeVisible();

  await page.getByTestId('ff-doc-dialog-close').click();
  await expect(page.getByTestId('ff-inbound-queue-row').first()).toHaveAttribute(
    'data-request-id',
    created.id,
  );
});

// TC-NEW-REC-LIST-001 — REC-10/REC-13/REC-14: список приёмок фильтруется, ищет по товару, сортируется
// и помечает расхождение. Решение заказчика 17.08.2026: подсветки строки нет — расхождение показывается
// красным текстом в колонке «Состав». Атрибут data-row-discrepancy на строке остаётся (невидимый, для теста).
test('ff reception list has filters search sorting and discrepancy marking', async ({ page }) => {
  const suffix = String(Date.now());
  const email = `e2e-rec-list-${suffix}@example.com`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Reception List');
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
    data: { name: 'Склад списка', code: `rec-list-${suffix}` },
  });
  expect(wh.ok()).toBeTruthy();
  const warehouseId = String(((await wh.json()) as { id: string }).id);

  async function createSellerProduct(name: string, sku: string) {
    const seller = await page.request.post('/api/sellers', {
      headers: h,
      data: { name },
    });
    expect(seller.ok()).toBeTruthy();
    const sellerId = String(((await seller.json()) as { id: string }).id);
    const product = await page.request.post('/api/products', {
      headers: h,
      data: {
        name: `${name} product`,
        sku_code: sku,
        seller_id: sellerId,
        length_mm: 10,
        width_mm: 10,
        height_mm: 10,
      },
    });
    expect(product.ok()).toBeTruthy();
    return { sellerId, productId: String(((await product.json()) as { id: string }).id) };
  }

  async function createRequest(opts: {
    sellerId: string;
    productId: string;
    plannedDate: string;
    expectedQty: number;
    actualQty?: number;
  }) {
    const base = '/api/operations/inbound-intake-requests';
    const created = await page.request.post(base, {
      headers: h,
      data: {
        warehouse_id: warehouseId,
        seller_id: opts.sellerId,
        planned_delivery_date: opts.plannedDate,
      },
    });
    expect(created.ok()).toBeTruthy();
    const requestId = String(((await created.json()) as { id: string }).id);
    const line = await page.request.post(`${base}/${requestId}/lines`, {
      headers: h,
      data: { product_id: opts.productId, expected_qty: opts.expectedQty },
    });
    expect(line.ok()).toBeTruthy();
    const lineId = String(((await line.json()) as { id: string }).id);
    await page.request.patch(`${base}/${requestId}`, {
      headers: h,
      data: { planned_box_count: 1 },
    });
    await page.request.post(`${base}/${requestId}/submit`, { headers: h });
    if (opts.actualQty != null) {
      await page.request.post(`${base}/${requestId}/begin-receiving`, { headers: h });
      await page.request.patch(`${base}/${requestId}/lines/${lineId}/actual`, {
        headers: h,
        data: { actual_qty: opts.actualQty },
      });
      await page.request.post(`${base}/${requestId}/verify`, { headers: h });
    }
    return requestId;
  }

  const red = await createSellerProduct(`REC Red Seller ${suffix}`, `REC-RED-${suffix}`);
  const green = await createSellerProduct(`REC Green Seller ${suffix}`, `REC-GREEN-${suffix}`);
  const fresh = await createSellerProduct(`REC Fresh Seller ${suffix}`, `REC-FRESH-${suffix}`);
  const redId = await createRequest({
    sellerId: red.sellerId,
    productId: red.productId,
    plannedDate: '2026-08-20',
    expectedQty: 5,
    actualQty: 4,
  });
  const greenId = await createRequest({
    sellerId: green.sellerId,
    productId: green.productId,
    plannedDate: '2026-08-18',
    expectedQty: 3,
    actualQty: 3,
  });
  const freshId = await createRequest({
    sellerId: fresh.sellerId,
    productId: fresh.productId,
    plannedDate: '2026-08-19',
    expectedQty: 7,
  });

  await page.goto('/app/ff/reception');
  await expect(page.getByRole('heading', { name: 'Приёмка на FF' })).toBeVisible();
  await expect(page.getByTestId('nav-ff-reception')).toContainText('Приёмка на FF');
  await expect(page.getByTestId('ff-inbound-new-count')).toContainText('Новые приёмки: 1');
  await expect(page.getByTestId('ff-inbound-queue-table')).toContainText('Селлер');
  await expect(page.getByTestId('ff-inbound-queue-table')).toContainText('Номер документа');
  await expect(page.getByTestId('ff-inbound-queue-table')).toContainText('Дата');
  await expect(page.getByTestId('ff-inbound-queue-table')).toContainText('Состав');
  await expect(page.getByTestId('ff-inbound-queue-table')).toContainText('Статус');

  const redRow = page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${redId}"]`);
  const greenRow = page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${greenId}"]`);
  const freshRow = page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${freshId}"]`);
  // redId принят с actual_qty=4 при expected_qty=5 — расхождение, строка помечена.
  // greenId принят ровно по плану (actual_qty=3 из 3) — расхождения нет, пометки нет.
  await expect(redRow).toHaveAttribute('data-row-discrepancy', 'yes');
  await expect(greenRow).toHaveAttribute('data-row-discrepancy', 'no');
  await expect(freshRow).toHaveAttribute('data-row-status', 'submitted');
  await expect(freshRow.getByTestId('ff-inbound-queue-composition')).toContainText('0 из 1 короба');
  await expect(freshRow.getByTestId('ff-inbound-queue-composition')).toContainText('7 ед.');

  await page.getByTestId('ff-inbound-search').fill(`REC-RED-${suffix}`);
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(redRow).toBeVisible();
  await page.getByTestId('ff-inbound-search').fill('');

  await page.getByTestId('ff-inbound-seller-filter').click();
  await page.getByRole('option', { name: `REC Green Seller ${suffix}` }).click();
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(greenRow).toBeVisible();
  await page.getByTestId('ff-inbound-seller-filter').click();
  await page.getByRole('option', { name: 'Все селлеры' }).click();

  await page.getByTestId('ff-inbound-status-filter').click();
  await page.getByRole('option', { name: 'Передано на склад' }).click();
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(freshRow).toBeVisible();
  await page.getByTestId('ff-inbound-status-filter').click();
  await page.getByRole('option', { name: 'Все статусы' }).click();

  await page.getByTestId('ff-inbound-sort-date').click();
  await expect(page.getByTestId('ff-inbound-queue-row').first()).toHaveAttribute(
    'data-request-id',
    greenId,
  );
  await page.getByTestId('ff-inbound-sort-number').click();
  await expect(page.getByTestId('ff-inbound-queue-row').first()).toBeVisible();
});

// TC-S06-007 — остаток после verify (зона сортировки); раскладка → доступно в ячейках.
test('ff verify posts to sorting zone; sorting queue and product columns', async ({ page }) => {
  const email = `e2e-sort-${Date.now()}@example.com`;
  const sku = `SKU-SORT-${Date.now()}`;
  const whCode = `wh-sort-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sort');
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
    data: { code: 'STORE-1' },
  });
  expect(loc.ok()).toBeTruthy();

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  const rid = ((await cr.json()) as { id: string }).id;
  await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 4 },
  });
  await page.request.patch(`${base}/${rid}`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { planned_box_count: 1 },
  });
  await page.request.post(`${base}/${rid}/submit`, { headers: h });

  await page.goto('/app/ff/reception');
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-row').first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/begin-receiving')),
    page.getByTestId('ff-inbound-submit-warehouse').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Приёмка');

  await expandInboundPackages(page);
  await page.getByTestId('ff-inbound-add-to-box').click();
  await page.getByTestId('ff-inbound-box-row').first().getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
  for (let i = 0; i < 4; i++) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(sku);
    await Promise.all([
      waitForPostOk(page, base, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ]);
  }
  await page.getByTestId('ff-inbound-box-add-dismiss').click();
  await Promise.all([
    waitForPostOk(page, base, (u) => u.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ]);

  await expect(page.getByTestId('ff-inbound-moved-to-sorting')).toBeVisible();
  await page.getByTestId('ff-doc-dialog-close').click();

  const balAfterVerify = await page.request.get('/api/operations/inventory-balances/summary', {
    headers: h,
  });
  expect(balAfterVerify.ok()).toBeTruthy();
  const row = ((await balAfterVerify.json()) as { product_id: string; quantity_in_sorting: number }[]).find(
    (r) => r.product_id === pid,
  );
  expect(row?.quantity_in_sorting).toBe(4);

  await page.goto('/app/ff/sorting');
  await expect(page.getByTestId('ff-sorting-page')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-queue-row')).toHaveCount(1);
  await expect(page.getByTestId('ff-inbound-queue-sorting-qty').first()).toHaveText('4');

  await page.getByTestId('ff-inbound-queue-row').first().click();
  // Экран сортировки внутри документа теста отстал от коммита 79fb36dd
  // «раскладка по ячейкам внутри документа сортировки»: владелец дважды
  // потребовал, чтобы это была именно раскладка объектами (FfSortingObjectsPage,
  // /app/ff/sorting-objects), а не карточки FfInboundSortingPanel с выбором
  // ячейки в select и кнопкой «Разложен» — тот компонент больше нигде не
  // монтируется. Ищем сразу дерево объектов новой раскладки.
  const objectsTree = page.getByTestId('objects-tree');
  await expect(objectsTree).toBeVisible();

  // Товар принят целым коробом, поэтому раскладываем сам короб без повторной
  // построчной раскладки его содержимого.
  const boxRow = objectsTree.getByRole('row', { name: /Короб/ });
  await expect(boxRow).toContainText('Короб');
  // IconAction прячет доступное имя кнопки на обёртке Tooltip (role=generic),
  // а не на самой кнопке — getByRole('button', { name }) её не находит.
  // Кнопка помечена префиксным data-testid `objects-tree-place-<rowKey>`.
  await boxRow.locator('[data-testid^="objects-tree-place-"]').click();
  await expect(page.getByTestId('objects-qty-dialog')).toBeVisible();
  await page.getByRole('combobox', { name: 'Место' }).selectOption({ label: 'Ячейка STORE-1' });
  await Promise.all([
    waitForPostOk(page, '/sorting-objects/place'),
    page.getByTestId('objects-qty-confirm').click(),
  ]);
  await expect(page.getByText('Всё расставлено по ячейкам')).toBeVisible();

  // ПОДТВЕРЖДЁННЫЙ БЭКЕНД-ДЕФЕКТ (не тест устарел): POST /warehouses/{id}/sorting-objects/place
  // для короба приёмки (InboundIntakeBox) отвечает 200 и moved_qty: 0 — «переставлено», а
  // фактически ничего. Причина: warehouse_map_service._container_balances ищет
  // InventoryBalance с container_kind='box' AND container_id=<box.id>, а приёмка
  // (complete-receiving) кладёт отсканированный в короб товар в зону сортировки БЕЗ
  // привязки container_kind/container_id к этому коробу (проверено прямым запросом к
  // inventory_balances в e2e-базе: container_kind/container_id пустые). Экран считает
  // короб «разложенным» (UI сам передвигает строку и показывает пустое состояние), но
  // остаток физически остаётся в зоне сортировки. Это расхождение экрана и склада —
  // ровно то, о чём предупреждает CLAUDE.md (учёт склада стоит денег и товара). Раньше
  // это делала выделенная ручка POST .../boxes/{id}/putaway (см. git-историю
  // FfInboundSortingPanel), она сюда не перенесена. Дальше assert намеренно ломается —
  // не подгонять его под «moved_qty: 0», это будет ложным зелёным.
  const balDone = await page.request.get('/api/operations/inventory-balances/summary', { headers: h });
  const doneRow = ((await balDone.json()) as {
    product_id: string;
    quantity_in_sorting: number;
    quantity_in_storage: number;
    available: number;
  }[]).find((r) => r.product_id === pid);
  expect(doneRow?.quantity_in_sorting).toBe(0);
  expect(doneRow?.quantity_in_storage).toBe(4);
  expect(doneRow?.available).toBe(4);

  await page.goto('/app/ff/products');
  await expect(page.getByTestId('ff-products-list')).toBeVisible();
  const prodRow = page.getByTestId('ff-product-row').filter({ hasText: sku });
  await expect(prodRow).toBeVisible();
  const catalogHead = page.getByTestId('ff-products-table').locator('thead');
  await expect(catalogHead).toContainText('Название');
  await expect(catalogHead).toContainText('Артикул продавца');
  await expect(catalogHead).toContainText('SKU');
  await expect(catalogHead).toContainText('ШК');
  await expect(catalogHead).toContainText('Размер');
  await expect(catalogHead).not.toContainText('Доступно');
  await expect(catalogHead).not.toContainText('Распределение');
  await expect(prodRow).toContainText(sku);
  await expect(page.getByTestId('ff-products-table')).not.toContainText('Сортировка');

  // TC-NEW-PRINT-03 — печать из каталога: единый диалог MarkingPrintDialog.
  await prodRow.getByRole('button', { name: 'Печать ШК товара' }).click();
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible();
  await expect(page.getByTestId('marking-print-wb-qty')).toBeVisible();
  await page.getByTestId('marking-print-dialog').getByRole('button', { name: 'Отмена' }).click();
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden();
});
