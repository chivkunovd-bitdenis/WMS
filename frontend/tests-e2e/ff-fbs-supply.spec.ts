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
  deliveryType = 'warehouse_sc',
  barcodeAsset = null,
  operatorFinishedAt = null,
  packingBoxes = [],
  unassignedOrderIds = [],
}: {
  stage?: string
  status?: string
  orders?: JsonObject[]
  deliveryType?: 'warehouse_sc' | 'pvz'
  barcodeAsset?: JsonObject | null
  operatorFinishedAt?: string | null
  packingBoxes?: JsonObject[]
  unassignedOrderIds?: string[]
} = {}): JsonObject {
  return {
    supply: {
      id: 'sup-1',
      wb_supply_id: 'WB-GI-MOCK-1',
      name: 'Тестовая поставка',
      status,
      delivery_type: deliveryType,
      seller: { id: 's-1', name: 'Селлер Один' },
      wb_warehouse: { id: 501001, name: 'WB Подольск' },
      wms_warehouse: { id: 'w-1', name: 'Основной склад' },
      planned_destination: null,
      nearest_deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
      packaging_task_id: null,
      barcode_asset: barcodeAsset,
      operator_finished_at: operatorFinishedAt,
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
    packing_boxes: packingBoxes,
    unassigned_order_ids: unassignedOrderIds,
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

test('fbs workspace: electronic WB fix, supply QR, then local finish', async ({ page }) => {
  await registerFf(page, 'deliver')
  const suppliedOrder = order('1', {
    status: 'packed',
    supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  })
  await mockWorklist(page, [suppliedOrder])

  const supplyQr = { id: 'asset-supply-qr', kind: 'supply_qr', status: 'ready', content_type: 'image/png', width_mm: 58, height_mm: 40, preview_url: '/qr.png', download_url: '/qr.png', checksum: 'qr', applied_at: '2026-08-06T09:00:00Z', error: null }
  let currentWorkspace = workspace({ stage: 'delivery', status: 'packed', orders: [suppliedOrder] })
  let deliverBody: JsonObject | null = null
  let finishBody: JsonObject | null = null
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
    currentWorkspace = workspace({ stage: 'local_finish', status: 'in_delivery', orders: [suppliedOrder], barcodeAsset: supplyQr })
    await json(route, currentWorkspace)
  })
  await page.route('**/operations/fbs-supplies/sup-1/finish', async (route) => {
    finishBody = route.request().postDataJSON() as JsonObject
    currentWorkspace = workspace({ stage: 'tracking', status: 'in_delivery', orders: [suppliedOrder], barcodeAsset: supplyQr, operatorFinishedAt: '2026-08-06T09:05:00Z' })
    await json(route, currentWorkspace)
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await page.getByTestId('fbs-order-1').click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(4)
  await expect(page.getByRole('tab', { name: 'Стикеры WB' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Подготовка к сдаче' })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Сдача в WB', exact: true }).click()
  await page.getByTestId('fbs-delivery-prepare').click()
  await page.getByRole('dialog', { name: 'Зафиксировать состав поставки?' }).getByRole('button', { name: 'Зафиксировать в WB' }).click()
  await expect(page.getByTestId('fbs-supply-qr')).toBeVisible()
  await expect(page.getByTestId('fbs-local-finish')).toBeEnabled()
  await page.getByTestId('fbs-local-finish').click()
  await expect(page.getByText(/Работа с поставкой завершена/).last()).toBeVisible()
  expect(deliverBody?.confirmed_preflight_version).toBe('preflight-v1')
  expect(deliverBody?.idempotency_key).toEqual(expect.any(String))
  expect(finishBody?.idempotency_key).toEqual(expect.any(String))
})

// TC-S17-006 — compatible selection creates one atomic supply and opens its workspace.
test('fbs orders: create supply from selected orders', async ({ page }) => {
  await registerFf(page, 'create')
  const selectedOrders = [order('1'), order('2')]
  await mockWorklist(page, selectedOrders)
  let createBody: JsonObject | null = null

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

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').getByRole('checkbox').click()
  await page.getByTestId('fbs-order-2').getByRole('checkbox').click()
  await expect(page.getByTestId('fbs-selection-bar')).toBeVisible()
  await page.getByRole('button', { name: 'Сформировать поставку' }).click()
  await expect(page.getByText('Можно создать поставку')).toBeVisible()
  await expect(page.getByTestId('fbs-create-submit')).toBeEnabled()
  await page.getByTestId('fbs-create-submit').click()

  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  expect(createBody?.order_ids).toEqual(['1', '2'])
  expect(createBody?.idempotency_key).toEqual(expect.any(String))
})

test('fbs workspace: manual pick by selected location without scanner', async ({ page }) => {
  await registerFf(page, 'pick')
  const pendingOrder = order('1', { status: 'in_supply', supply_id: 'sup-1' })
  await mockWorklist(page, [pendingOrder])
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, workspace({ stage: 'picking', status: 'assembling', orders: [pendingOrder] })),
  )
  let scannerCalls = 0
  page.on('request', (request) => { if (request.url().includes('/pick/scan-')) scannerCalls += 1 })
  await page.route('**/operations/fbs-supplies/sup-1/pick/resolve-location', (route) =>
    json(route, {
      id: 'loc-1',
      code: 'A-01',
      warehouse_id: 'w-1',
      warehouse_name: 'Основной склад',
      expected_products: [],
    }),
  )
  await page.route('**/operations/fbs-supplies/sup-1/pick/confirm-product', (route) =>
    json(route, workspace({
      stage: 'packing',
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
  await expect(page.getByText('Сканер для этого не требуется.')).toBeVisible()
  await page.getByLabel('Ячейка для заказа WB №1').click()
  await page.getByRole('option', { name: /A-01/ }).click()
  await page.getByTestId('fbs-manual-pick-1').getByRole('button', { name: 'Снять с ячейки' }).click()
  await expect(page.getByRole('tab', { name: 'Упаковка и маркировка' })).toHaveAttribute('aria-selected', 'true')
  expect(scannerCalls).toBe(0)
})

test('fbs workspace: local boxes assign, unassign and delete an empty box', async ({ page }) => {
  await registerFf(page, 'boxes')
  const packedOrders = ['1', '2'].map((id) => order(id, {
    status: 'packed', supply_id: 'sup-1',
    pick: { status: 'picked', location_code: 'A-01', picked_at: new Date().toISOString() },
    pack: { status: 'packed', packed_at: new Date().toISOString() },
  }))
  await mockWorklist(page, packedOrders)
  const box = (id: string, boxNumber: number, orders: JsonObject[] = []): JsonObject => ({ id, box_number: boxNumber, status: 'open', internal_barcode: `BOX-${boxNumber}`, wb_trbx_id: null, qr_asset: null, items_count: orders.length, orders })
  const packedBoxOrder = (id: string): JsonObject => ({ id, wb_order_id: Number(id), product_id: `p-${id}`, product_name: `Товар ${id}` })
  let currentWorkspace = workspace({ stage: 'packing', status: 'packed', orders: packedOrders, unassignedOrderIds: ['1', '2'] })
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) => json(route, currentWorkspace))
  await page.route('**/operations/fbs-supplies/sup-1/packing-boxes', async (route) => {
    if (route.request().method() === 'POST') currentWorkspace = workspace({ stage: 'packing', status: 'packed', orders: packedOrders, packingBoxes: [box('box-1', 1), box('box-2', 2)], unassignedOrderIds: ['1', '2'] })
    await json(route, currentWorkspace, route.request().method() === 'POST' ? 201 : 200)
  })
  await page.route('**/operations/fbs-supplies/sup-1/packing-boxes/box-1/orders', async (route) => {
    currentWorkspace = route.request().method() === 'PUT'
      ? workspace({ stage: 'packing', status: 'packed', orders: packedOrders, packingBoxes: [box('box-1', 1, [packedBoxOrder('1')]), box('box-2', 2)], unassignedOrderIds: ['2'] })
      : workspace({ stage: 'packing', status: 'packed', orders: packedOrders, packingBoxes: [box('box-1', 1), box('box-2', 2)], unassignedOrderIds: ['1', '2'] })
    await json(route, currentWorkspace)
  })
  await page.route('**/operations/fbs-supplies/sup-1/packing-boxes/box-2', async (route) => {
    currentWorkspace = workspace({ stage: 'packing', status: 'packed', orders: packedOrders, packingBoxes: [box('box-1', 1)], unassignedOrderIds: ['1', '2'] })
    await json(route, currentWorkspace)
  })
  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').click()
  await page.getByRole('tab', { name: 'Упаковка и маркировка' }).click()
  await page.getByLabel('Количество коробов').fill('2')
  await page.getByTestId('fbs-boxes-create').click()
  const boxes = page.getByTestId('fbs-packing-boxes')
  const table = page.getByTestId('fbs-boxes-table')
  await expect(boxes.getByText('Не распределено: 1')).toHaveCount(2)
  await boxes.getByRole('button', { name: 'Положить в короб' }).first().click()
  await expect(table.getByText('Товар 1 · заказ WB №1')).toBeVisible()
  await expect(boxes.getByText('Не распределено: 1')).toHaveCount(1)
  await table.getByRole('button', { name: 'Убрать' }).click()
  await expect(table.getByText('Товар 1 · заказ WB №1')).toHaveCount(0)
  await boxes.getByLabel('Удалить короб 2').click()
  await page.getByTestId('fbs-box-delete-confirm').click()
  await expect(table.getByText('Короб 2', { exact: true })).toHaveCount(0)
})
