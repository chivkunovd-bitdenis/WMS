import { expect, test, type Page, type Route } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

type JsonObject = Record<string, unknown>

function order(id: string, over: JsonObject = {}): JsonObject {
  return {
    id,
    wb_order_id: Number(id.replace(/\D/g, '') || '1'),
    status: 'new',
    wb_status: 'waiting',
    seller: { id: 's-1', name: 'Селлер Один' },
    wb_warehouse: { id: 501001, name: 'WB Подольск' },
    wms_warehouse: { id: 'w-1', name: 'Основной склад' },
    product: {
      id: `p-${id}`,
      name: `Товар ${id}`,
      image_url: null,
      seller_article: `ART-${id}`,
      wb_article: 1000 + Number(id.replace(/\D/g, '') || '1'),
      barcode: `200000${id}`,
      sku: `SKU-${id}`,
      chrt_id: 7000 + Number(id.replace(/\D/g, '') || '1'),
      category: 'Бомберы',
      color: null,
      size: null,
    },
    inventory: {
      available_unpacked: 3,
      locations: [{ id: 'loc-1', code: 'A-01', available_unpacked: 3 }],
    },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: true,
    metadata: {
      required: [],
      optional: [],
      states: [],
      delivery_allowed: true,
      last_checked_at: null,
    },
    sticker: { status: 'applied', asset_url: null, applied_at: new Date().toISOString() },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
    supply_id: null,
    selection_blockers: [],
    ...over,
  }
}

function workspace({
  stage = 'composition',
  status = 'draft',
  orders = [order('1', { supply_id: 'sup-1' })],
}: {
  stage?: string
  status?: string
  orders?: JsonObject[]
} = {}): JsonObject {
  return {
    supply: {
      id: 'sup-1',
      wb_supply_id: 'WB-GI-MOCK-1',
      name: 'Тестовая поставка',
      status,
      delivery_type: 'warehouse_sc',
      seller: { id: 's-1', name: 'Селлер Один' },
      wb_warehouse: { id: 501001, name: 'WB Подольск' },
      wms_warehouse: { id: 'w-1', name: 'Основной склад' },
      planned_destination: null,
      planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
      packaging_task_id: null,
      barcode_asset: null,
    },
    stage,
    progress: {
      picked: orders.filter((item) => (item.pick as JsonObject).status === 'picked').length,
      packed: orders.filter((item) => (item.pack as JsonObject).status === 'packed').length,
      metadata_ready: orders.length,
      stickers_ready: orders.length,
      total: orders.length,
    },
    blockers: [],
    orders,
    cargo_places: [],
    boxes: [],
    marking_pool: { required: 0, available: 0, shortage: 0, orders_without_code: [] },
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: new Date().toISOString(),
    tracking_summary: null,
    partial_rejection: null,
    wb_sync_stale: false,
  }
}

function worklist(items: JsonObject[]): JsonObject {
  return { items, next_cursor: null, server_now: new Date().toISOString() }
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function registerFf(page: Page, tag: string) {
  const email = `e2e-fbs-sup-${tag}-${Date.now()}@example.com`
  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`E2E FBS SUP ${tag}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  await expect(page.getByTestId('dashboard')).toBeVisible()
}

async function mockWorklist(page: Page, items: JsonObject[]) {
  await page.route('**/operations/fbs-orders/worklist**', (route) =>
    route.request().method() === 'GET' ? json(route, worklist(items)) : route.fallback(),
  )
}

function supplyWorklistRow(id: string, over: JsonObject = {}): JsonObject {
  return {
    id,
    wb_supply_id: `WB-GI-MOCK-${id}`,
    name: 'Тестовая поставка',
    status: 'assembling',
    seller: { id: 's-1', name: 'Селлер Один' },
    wb_warehouse: { id: 501001, name: 'WB Подольск' },
    wms_warehouse: { id: 'w-1', name: 'Основной склад' },
    orders_count: 1,
    units_count: 1,
    boxes_count: 0,
    planned_shipment_date: null,
    can_add_orders: false,
    ...over,
  }
}

async function mockSupplyWorklist(page: Page, items: JsonObject[]) {
  await page.route('**/operations/fbs-supplies/worklist**', (route) =>
    route.request().method() === 'GET'
      ? json(route, { items, server_now: new Date().toISOString() })
      : route.fallback(),
  )
}

type PickingItem = {
  article: string
  sku_code: string | null
  size: string | null
  product_name: string
  quantity: number
  number_start: number
  number_end: number
  order_ids: string[]
}

const PICKING_ITEMS: PickingItem[] = [
  { article: 'ART-001', sku_code: 'SKU-001', size: 'M', product_name: 'Футболка базовая', quantity: 3, number_start: 1, number_end: 3, order_ids: ['order-1', 'order-2', 'order-3'] },
  { article: 'CAP-017', sku_code: 'SKU-017', size: null, product_name: 'Кепка хлопковая', quantity: 1, number_start: 4, number_end: 4, order_ids: ['order-4'] },
  { article: 'HD-402', sku_code: 'SKU-402', size: 'L', product_name: 'Худи утеплённое', quantity: 2, number_start: 5, number_end: 6, order_ids: ['order-5', 'order-6'] },
]

async function openPickingList(page: Page, tag: string, items: PickingItem[]) {
  await registerFf(page, tag)
  const orderIds = items.flatMap((item) => item.order_ids)
  const workspaceOrderIds = orderIds.length > 0 ? [...orderIds].reverse() : ['empty-anchor']
  const suppliedOrders = workspaceOrderIds.map((id) => order(id, {
    status: 'in_supply',
    supply_id: 'sup-1',
  }))

  await mockWorklist(page, suppliedOrders)
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, workspace({ stage: 'picking', status: 'assembling', orders: suppliedOrders })),
  )
  await page.route('**/operations/fbs-supplies/sup-1/picking-list', (route) =>
    json(route, { items }),
  )

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId(`fbs-order-${workspaceOrderIds[0]}`).click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByTestId('fbs-pick-list-print').click()
  await expect(page.getByTestId('fbs-pick-list')).toBeVisible()
  return page.getByTestId('fbs-pick-list')
}

function readyTape(orderIds: string[]): JsonObject {
  return {
    requested: orderIds.length,
    ready: orderIds.length,
    missing: 0,
    failed: 0,
    shortage: 0,
    order_errors: [],
    orders: orderIds.map((orderId, index) => ({
      order_id: orderId,
      wb_order_id: 845000 + index,
      order_number: index + 1,
      requires_honest_sign: false,
      qr_asset: {
        id: `asset-${orderId}`,
        kind: 'order_sticker',
        status: 'ready',
        content_type: 'image/png',
        width_mm: 40,
        height_mm: 58,
        preview_url: `/operations/fbs-print-assets/asset-${orderId}/content`,
        download_url: null,
        checksum: `sha256:${orderId}`,
        applied_at: null,
        error: null,
      },
      codes: [],
      printed_codes: [],
      shortage: null,
    })),
  }
}

async function mockStickerImages(page: Page) {
  await page.route('**/operations/fbs-print-assets/asset-*/content', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/l9sZ3wAAAABJRU5ErkJggg==',
        'base64',
      ),
    }),
  )
}

// S-03-TC-001 — оператор открывает реальную модалку и видит серверный порядок с постоянными диапазонами.
test('S-03-TC-001: picking list shows canonical ranges in server order', async ({ page }) => {
  const dialog = await openPickingList(page, 'pick-list-order', PICKING_ITEMS)
  const table = dialog.getByTestId('fbs-pick-table')
  const rows = table.locator('tbody tr')

  await expect(table.getByRole('columnheader')).toHaveText(['№', 'Товар', 'Размер', 'Кол-во', 'Собрал', 'Упаковал'])
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toContainText('1–3')
  await expect(rows.nth(0)).toContainText('Футболка базовая')
  await expect(rows.nth(1)).toContainText('4')
  await expect(rows.nth(1)).toContainText('Кепка хлопковая')
  await expect(rows.nth(2)).toContainText('5–6')
  await expect(rows.nth(2)).toContainText('Худи утеплённое')
})

// S-03-TC-002 — локальная отметка и фильтр скрывают строку, но не перенумеровывают оставшиеся.
test('S-03-TC-002: local mark and filter preserve original ranges', async ({ page }) => {
  const dialog = await openPickingList(page, 'pick-list-filter', PICKING_ITEMS)
  const table = dialog.getByTestId('fbs-pick-table')
  const originalRows = table.locator('tbody tr')

  await originalRows.nth(1).getByTestId('fbs-pick-collected').locator('input').check()
  await dialog.getByRole('button', { name: 'Не собраны' }).click()

  const visibleRows = table.locator('tbody tr')
  await expect(visibleRows).toHaveCount(2)
  await expect(visibleRows.nth(0)).toContainText('1–3')
  await expect(visibleRows.nth(1)).toContainText('5–6')
  await expect(table).not.toContainText('Кепка хлопковая')

  await dialog.getByTestId('filter-search').fill('Худи')
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await expect(table.locator('tbody tr').first()).toContainText('5–6')
})

// S-03-TC-003 — пустой результат фильтра не превращает полную печать в выборочную.
test('S-03-TC-003: empty filter result still prints the full canonical supply', async ({ page }) => {
  const dialog = await openPickingList(page, 'pick-list-full-print', PICKING_ITEMS)
  const canonicalOrderIds = PICKING_ITEMS.flatMap((item) => item.order_ids)
  let printBody: JsonObject | null = null
  await mockStickerImages(page)
  await page.route('**/operations/fbs-supplies/sup-1/order-print-tape', async (route) => {
    printBody = route.request().postDataJSON() as JsonObject
    await json(route, readyTape(canonicalOrderIds))
  })

  for (const checkbox of await dialog.getByTestId('fbs-pick-collected').all()) {
    await checkbox.locator('input').check()
  }
  await dialog.getByRole('button', { name: 'Не собраны' }).click()
  await expect(dialog.getByText('Нет позиций по фильтру')).toBeVisible()

  await dialog.getByTestId('fbs-pick-print-stickers').click()
  await expect(page.getByRole('dialog', { name: 'Проверка перед печатью' })).toBeVisible()
  expect(printBody?.order_ids).toEqual(canonicalOrderIds)
  expect(printBody?.include_order_qr).toBe(true)
})

// S-03-TC-006 — пустая поставка объяснена, печать недоступна с контрактной причиной.
test('S-03-TC-006: empty supply explains why there is nothing to pick or print', async ({ page }) => {
  const dialog = await openPickingList(page, 'pick-list-empty', [])

  await expect(dialog.getByText('В поставке нет позиций для подбора')).toBeVisible()
  await expect(dialog.getByText('Закройте лист и проверьте состав поставки')).toBeVisible()
  await expect(dialog.getByTestId('fbs-pick-print-stickers')).toBeDisabled()
})

// S-03-TC-007 — пока сервер готовит ленту, повторный запуск и закрытие модалки заблокированы.
test('S-03-TC-007: print preparation blocks duplicate print and closing', async ({ page }) => {
  const dialog = await openPickingList(page, 'pick-list-busy', PICKING_ITEMS.slice(0, 1))
  const canonicalOrderIds = PICKING_ITEMS[0].order_ids
  let releasePrint!: () => void
  const printGate = new Promise<void>((resolve) => { releasePrint = resolve })
  let printRequests = 0
  await mockStickerImages(page)
  await page.route('**/operations/fbs-supplies/sup-1/order-print-tape', async (route) => {
    printRequests += 1
    await printGate
    await json(route, readyTape(canonicalOrderIds))
  })

  await dialog.getByTestId('fbs-pick-print-stickers').click()
  await expect.poll(() => printRequests).toBe(1)
  await expect(dialog.getByTestId('fbs-pick-print-stickers')).toBeDisabled()
  await expect(dialog.getByRole('button', { name: 'Закрыть' })).toBeDisabled()
  await dialog.getByTestId('fbs-pick-print-stickers').dispatchEvent('click')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  expect(printRequests).toBe(1)

  releasePrint()
  await expect(page.getByRole('dialog', { name: 'Проверка перед печатью' })).toBeVisible()
  expect(printRequests).toBe(1)
})

// TC-S17-019 / TC-S17-021 — fresh preflight and idempotent warehouse/SC delivery.
test('fbs workspace: preflight and deliver', async ({ page }) => {
  await registerFf(page, 'deliver')
  const suppliedOrder = order('1', {
    status: 'packed',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  await mockWorklist(page, [suppliedOrder])

  let currentWorkspace = workspace({ stage: 'delivery', status: 'packed', orders: [suppliedOrder] })
  let deliverBody: JsonObject | null = null
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, currentWorkspace),
  )
  await page.route('**/operations/fbs-supplies/sup-1/delivery-preflight', (route) =>
    json(route, {
      can_deliver: true,
      version: 'preflight-v1',
      checked_at: new Date().toISOString(),
      checks: [{ code: 'ready', message: 'Поставка готова', ok: true, order_id: null }],
    }),
  )
  await page.route('**/operations/fbs-supplies/sup-1/deliver', async (route) => {
    deliverBody = route.request().postDataJSON() as JsonObject
    currentWorkspace = workspace({ stage: 'tracking', status: 'in_delivery', orders: [suppliedOrder] })
    await json(route, currentWorkspace)
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await page.getByTestId('fbs-order-1').click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await expect(page.getByTestId('fbs-boxes')).toBeVisible()
  await page.getByRole('button', { name: 'Передать в WB' }).click()
  const deliverConfirmDialog = page.getByRole('dialog', { name: 'Передать поставку в WB?' })
  await expect(deliverConfirmDialog).toBeVisible()
  await deliverConfirmDialog.getByRole('button', { name: 'Передать в WB' }).click()

  await expect(page.getByText('Поставка передана, QR получить не удалось')).toBeVisible()
  expect(deliverBody?.confirmed_preflight_version).toBeUndefined()
  expect(deliverBody?.idempotency_key).toEqual(expect.any(String))
})

// TC-S17-006 — compatible selection creates one atomic supply and opens its workspace.
test('fbs orders: create supply from selected orders', async ({ page }) => {
  await registerFf(page, 'create')
  const selectedOrders = [order('1'), order('2')]
  await mockWorklist(page, selectedOrders)
  let createBody: JsonObject | null = null
  let plannedDateBody: JsonObject | null = null

  await page.route('**/operations/fbs-supplies/preflight', (route) =>
    json(route, {
      compatible: true,
      summary: {
        seller: { id: 's-1', name: 'Селлер Один' },
        wb_warehouse: { id: 501001, name: 'WB Подольск' },
        wms_warehouse: { id: 'w-1', name: 'Основной склад' },
        buyer_type: 'individual',
        cargo_type: 'mgt',
        orders_count: 2,
        required_marking_count: 0,
        pvz_allowed_count: 2,
        pvz_blocked_count: 0,
        nearest_deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
      },
      issues: [],
    }),
  )
  await page.route('**/operations/fbs-supplies/from-orders', async (route) => {
    createBody = route.request().postDataJSON() as JsonObject
    await json(route, workspace({ orders: selectedOrders.map((item) => ({ ...item, supply_id: 'sup-1' })) }), 201)
  })
  await page.route('**/operations/fbs-supplies/sup-1/planned-shipment-date', async (route) => {
    plannedDateBody = route.request().postDataJSON() as JsonObject
    const body = plannedDateBody as { planned_shipment_date?: string | null }
    const next = workspace({ orders: selectedOrders.map((item) => ({ ...item, supply_id: 'sup-1' })) })
    ;(next.supply as JsonObject).planned_shipment_date = body.planned_shipment_date ?? null
    await json(route, next)
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').getByRole('checkbox').click()
  await page.getByTestId('fbs-order-2').getByRole('checkbox').click()
  await expect(page.getByTestId('fbs-selection-bar')).toBeVisible()
  await page.getByRole('button', { name: 'Сформировать поставку' }).click()
  await expect(page.getByText('Можно создать поставку')).toBeVisible()
  await expect(page.getByTestId('fbs-create-submit')).toBeEnabled()
  await page.getByTestId('fbs-create-submit').click()

  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await expect(page.getByTestId('cal-02-fbs-shipment-date')).toBeVisible()
  await page.getByTestId('cal-02-fbs-shipment-date').fill('2026-08-17')
  await page.getByTestId('cal-02-fbs-shipment-date-save').click()
  await expect(page.getByText('Дата отгрузки сохранена.')).toBeVisible()
  expect(createBody?.order_ids).toEqual(['1', '2'])
  expect(createBody?.idempotency_key).toEqual(expect.any(String))
  expect(plannedDateBody).toEqual({ planned_shipment_date: '2026-08-17' })
})

// TC-NEW-FBS-PARTIAL-READBACK — WB partial confirmation remains visible after workspace read-back.
test('fbs workspace: partial rejection is visible outside composition stage', async ({ page }) => {
  await registerFf(page, 'partial-readback')
  const acceptedOrder = order('1', {
    status: 'sorted',
    wb_status: 'waiting',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  const rejectedOrder = order('2', {
    status: 'defect',
    wb_status: 'defect',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  await mockWorklist(page, [acceptedOrder])
  await mockSupplyWorklist(page, [supplyWorklistRow('sup-1', { status: 'in_delivery' })])
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, {
      ...workspace({
        stage: 'tracking',
        status: 'in_delivery',
        orders: [acceptedOrder, rejectedOrder],
      }),
      partial_rejection: {
        accepted_orders: [{ wb_order_id: 1, reason: null }],
        rejected_orders: [{ wb_order_id: 2, reason: 'Брак при приёмке маркетплейсом.' }],
      },
    }),
  )

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByRole('tab', { name: 'В доставке' }).click()
  await page.getByTestId('fbs-18-supply-sup-1').click()

  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await expect(page.getByTestId('fbs-partial-rejection')).toContainText('WB подтвердил только часть заказов')
  await expect(page.getByTestId('fbs-partial-rejection')).toContainText('№1')
  await expect(page.getByTestId('fbs-partial-rejection')).toContainText('№2')
})

// TC-S17-007 — location then product scan updates server-owned picking progress.
test('fbs workspace: scan location then product', async ({ page }) => {
  await registerFf(page, 'pick')
  const pendingOrder = order('1', { status: 'in_supply', supply_id: 'sup-1' })
  await mockWorklist(page, [pendingOrder])
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, workspace({ stage: 'picking', status: 'assembling', orders: [pendingOrder] })),
  )
  await page.route('**/operations/fbs-supplies/sup-1/pick/scan-location', (route) =>
    json(route, {
      id: 'loc-1',
      code: 'A-01',
      warehouse_id: 'w-1',
      warehouse_name: 'Основной склад',
      expected_products: [],
    }),
  )
  await page.route('**/operations/fbs-supplies/sup-1/pick/scan-product', (route) =>
    json(route, workspace({
      stage: 'picking',
      status: 'assembling',
      orders: [order('1', {
        status: 'in_supply',
        supply_id: 'sup-1',
        pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
      })],
    })),
  )

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByLabel('Штрихкод ячейки').fill('CELL-A-01')
  await page.getByRole('button', { name: 'Подтвердить ячейку' }).click()
  await expect(page.getByText(/Ячейка A-01 подтверждена/)).toBeVisible()
  await page.getByLabel('Штрихкод товара').fill('2000001')
  await page.getByRole('button', { name: 'Подобрать товар' }).click()

  await expect(page.getByText('Товар подобран. Прогресс синхронизирован для всех операторов.')).toBeVisible()
})

// TC-NEW-FBS-12 — boxes can be created in "without distribution" mode.
test('fbs workspace: boxes without distribution sends durable mode', async ({ page }) => {
  await registerFf(page, 'boxes-no-distribution')
  const packedOrder = order('1', {
    status: 'packed',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  await mockWorklist(page, [packedOrder])
  let currentWorkspace = workspace({ stage: 'handoff_prep', status: 'packed', orders: [packedOrder] })
  let createBody: JsonObject | null = null

  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) => json(route, currentWorkspace))
  await page.route('**/operations/fbs-supplies/sup-1/boxes', async (route) => {
    createBody = route.request().postDataJSON() as JsonObject
    currentWorkspace = {
      ...currentWorkspace,
      stage: 'delivery',
      boxes: [{
        id: 'box-1',
        box_number: 1,
        barcode: 'FBS-MOCK-001',
        assigned_order_ids: [],
        trbx_id: null,
        wb_trbx_id: null,
        qr_asset: null,
        without_distribution: true,
      }],
    }
    await json(route, currentWorkspace, 201)
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').click()
  await expect(page.getByTestId('fbs-boxes')).toBeVisible()
  await page.getByTestId('fbs-boxes-without-distribution').check()
  await page.getByLabel('Коробов').fill('2')
  await page.getByRole('button', { name: 'Добавить короба' }).click()

  expect(createBody?.without_distribution).toBe(true)
  expect(createBody?.count).toBe(2)
  await expect(page.getByText('Без распределения · коробов 1')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Добавить товары' })).toBeDisabled()
  await page.getByRole('button', { name: 'QR' }).click()
  const preview = page.getByRole('dialog', { name: 'Проверка перед печатью' })
  await expect(preview).toContainText('Печать QR короба WMS')
  await expect(preview.getByTestId('fbs-print-preview-copies')).toBeVisible()
})

// TC-NEW-FBS-10/FBS-09 — one print preview shows the asset and copy count before printing.
test('fbs workspace: supply QR preview has copies control', async ({ page }) => {
  await registerFf(page, 'qr-preview')
  const packedOrder = order('1', {
    status: 'packed',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  await mockWorklist(page, [packedOrder])
  const currentWorkspace = {
    ...workspace({ stage: 'tracking', status: 'in_delivery', orders: [packedOrder] }),
    supply: {
      ...(workspace({ stage: 'tracking', status: 'in_delivery', orders: [packedOrder] }).supply as JsonObject),
      barcode_asset: {
        id: 'asset-supply-qr',
        kind: 'supply_qr',
        status: 'ready',
        content_type: 'image/png',
        width_mm: 58,
        height_mm: 40,
        preview_url: '/operations/fbs-print-assets/asset-supply-qr/content',
        download_url: '/operations/fbs-print-assets/asset-supply-qr/content',
        checksum: 'sha256:mock',
        applied_at: null,
        error: null,
      },
    },
  }
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) => json(route, currentWorkspace))
  await mockSupplyWorklist(page, [supplyWorklistRow('sup-1', { status: 'in_delivery' })])
  await page.route('**/operations/fbs-print-assets/asset-supply-qr/content', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/l9sZ3wAAAABJRU5ErkJggg==',
        'base64',
      ),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByRole('tab', { name: 'В доставке' }).click()
  await page.getByTestId('fbs-18-supply-sup-1').click()
  await page.getByRole('button', { name: 'Печать QR поставки' }).click()

  const dialog = page.getByRole('dialog', { name: 'Проверка перед печатью' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('fbs-print-preview-copies')).toBeVisible()
  await dialog.getByLabel('Копий каждого макета').fill('3')
  await expect(dialog.getByLabel('Копий каждого макета')).toHaveValue('3')
})
