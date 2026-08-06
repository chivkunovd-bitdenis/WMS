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
  await page.getByTestId('fbs-order-1').getByRole('button', { name: 'Продолжить работу' }).click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByRole('tab', { name: 'Передача и статусы' }).click()
  await page.getByRole('button', { name: 'Проверить готовность' }).click()
  await expect(page.getByText('Поставка готова')).toBeVisible()
  await page.getByRole('button', { name: 'Подтвердить передачу WB' }).click()
  await page.getByRole('dialog', { name: 'Подтвердить передачу в WB?' }).getByRole('button', { name: 'Передать в WB' }).click()

  await expect(page.getByText('WB подтвердил передачу поставки в доставку.')).toBeVisible()
  expect(deliverBody?.confirmed_preflight_version).toBe('preflight-v1')
  expect(deliverBody?.idempotency_key).toEqual(expect.any(String))
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
  await page.getByTestId('fbs-order-1').getByRole('button', { name: 'Продолжить работу' }).click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByLabel('Штрихкод ячейки').fill('CELL-A-01')
  await page.getByRole('button', { name: 'Подтвердить ячейку' }).click()
  await expect(page.getByText(/Ячейка A-01 подтверждена/)).toBeVisible()
  await page.getByLabel('Штрихкод товара').fill('2000001')
  await page.getByRole('button', { name: 'Подобрать товар' }).click()

  await expect(page.getByText('Товар подобран. Прогресс синхронизирован для всех операторов.')).toBeVisible()
  await expect(page.getByText('Товары в подборе: 1/1')).toBeVisible()
})
