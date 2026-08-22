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
      verdict: {
        signature: 'WB: принято',
        tone: 'ok',
        reason: null,
        delivery_allowed: true,
      },
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
  packagingTaskId = null,
}: {
  stage?: string
  status?: string
  orders?: JsonObject[]
  packagingTaskId?: string | null
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
      packaging_task_id: packagingTaskId,
      barcode_asset: null,
    },
    stage,
    progress: {
      picked: orders.filter((item) => (item.pick as JsonObject).status === 'picked').length,
      packed: orders.filter((item) => (item.pack as JsonObject).status === 'packed').length,
      metadata_ready: orders.filter((item) =>
        (((item.metadata as JsonObject).verdict as JsonObject).delivery_allowed === true),
      ).length,
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

function packagingTask(orders: JsonObject[]): JsonObject {
  return {
    id: 'task-verdict',
    document_number: 'PACK-VERDICT',
    warehouse_id: 'w-1',
    status: 'in_progress',
    marketplace_unload_request_id: null,
    inbound_intake_request_id: null,
    is_complete: false,
    lines: orders.map((item, index) => {
      const product = item.product as JsonObject
      return {
        id: `line-${index + 1}`,
        product_id: product.id,
        sku_code: product.sku,
        product_name: product.name,
        storage_location_id: 'loc-1',
        storage_location_code: 'A-01',
        packaging_instructions: null,
        requires_honest_sign: true,
        qty_total: 1,
        qty_suggested_packed: 0,
        qty_confirmed_packed: 0,
        qty_need_pack: 1,
        qty_packed_in_task: 0,
        qty_done: 0,
        qty_marking_printed: 0,
        qty_marking_external: 0,
        qty_product_label_printed: 0,
        marking_available_count: 0,
        is_complete: false,
      }
    }),
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

async function openVerdictWorkspace(page: Page, tag: string, orders: JsonObject[]) {
  await registerFf(page, tag)
  await mockWorklist(page, orders)
  await page.route('**/operations/fbs-supplies/sup-1/workspace', (route) =>
    json(route, workspace({ stage: 'packing', status: 'packed', orders, packagingTaskId: 'task-verdict' })),
  )
  await page.route('**/operations/packaging-tasks/task-verdict', (route) =>
    json(route, packagingTask(orders)),
  )
  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await expect(page.getByTestId('fbs-kiz-scan-bar')).toBeVisible()
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

// S-03-TC-004 — server pending verdict is visible in the ЧЗ row and blocks delivery.
test('fbs workspace: pending WB verdict blocks delivery', async ({ page }) => {
  const pending = order('1', {
    supply_id: 'sup-1',
    metadata: {
      required: ['sgtin'], optional: [], states: [], delivery_allowed: false,
      verdict: { signature: 'WB: проверяет', tone: 'stop', reason: null, delivery_allowed: false },
      last_checked_at: new Date().toISOString(),
    },
  })
  await openVerdictWorkspace(page, 'verdict-pending', [pending])

  await expect(page.getByTestId('fbs-wb-verdict-1')).toHaveText('WB: проверяет')
  await expect(page.getByText('0 из 1 подготовлено к отгрузке')).toBeVisible()
  const deliver = page.getByRole('button', { name: 'Передать в WB' })
  await expect(deliver).toBeDisabled()
  await deliver.hover()
  await expect(page.getByRole('tooltip')).toContainText('Заказ №1: Сдача пока недоступна')
})

// S-03-TC-005 — required verdict tells the operator that a code is needed.
test('fbs workspace: required WB verdict explains missing code', async ({ page }) => {
  const required = order('1', {
    supply_id: 'sup-1',
    metadata: {
      required: ['sgtin'], optional: [], states: [], delivery_allowed: false,
      verdict: { signature: 'WB: нужен код', tone: 'stop', reason: null, delivery_allowed: false },
      last_checked_at: new Date().toISOString(),
    },
  })
  await openVerdictWorkspace(page, 'verdict-required', [required])

  await expect(page.getByTestId('fbs-wb-verdict-1')).toHaveText('WB: нужен код')
  await expect(page.getByText('0 из 1 подготовлено к отгрузке')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Передать в WB' })).toBeDisabled()
})

// S-03-TC-007 — one server-side blocker disables the whole supply and names its order.
test('fbs workspace: one blocked order prevents whole-supply delivery', async ({ page }) => {
  const accepted = order('1', {
    supply_id: 'sup-1',
    metadata: {
      required: ['sgtin'],
      optional: [],
      states: [{ kind: 'sgtin', status: 'accepted', value_tail: '…5678' }],
      delivery_allowed: true,
      verdict: { signature: 'WB: принято', tone: 'ok', reason: null, delivery_allowed: true },
      last_checked_at: new Date().toISOString(),
    },
  })
  const blocked = order('2', {
    supply_id: 'sup-1',
    metadata: {
      required: ['sgtin'],
      optional: [],
      states: [{ kind: 'sgtin', status: 'accepted', value_tail: '…1234' }],
      delivery_allowed: false,
      verdict: { signature: 'WB не принял', tone: 'stop', reason: 'uinBadStatus', delivery_allowed: false },
      last_checked_at: new Date().toISOString(),
    },
  })
  await openVerdictWorkspace(page, 'verdict-aggregate', [accepted, blocked])

  await expect(page.getByTestId('fbs-wb-verdict-2')).toHaveText('WB не принял')
  await expect(page.getByText('неверный статус УИН')).toBeVisible()
  await expect(page.getByText('1 из 2 подготовлено к отгрузке')).toBeVisible()
  await expect(page.getByText('2 из 2 подготовлено к отгрузке')).toHaveCount(0)
  await expect(page.getByTestId('fbs-order-print-done-2')).toHaveCount(0)
  // WB-вердикт транслируется только через StatusChip; строка остаётся нейтральной в обоих случаях.
  const acceptedRow = page.getByTestId('fbs-kiz-row-1')
  const blockedRow = page.getByTestId('fbs-kiz-row-2')
  const acceptedBg = await acceptedRow.evaluate((el) => window.getComputedStyle(el).backgroundColor)
  const blockedBg = await blockedRow.evaluate((el) => window.getComputedStyle(el).backgroundColor)
  const acceptedBorder = await acceptedRow.evaluate((el) => window.getComputedStyle(el).borderLeftColor)
  const blockedBorder = await blockedRow.evaluate((el) => window.getComputedStyle(el).borderLeftColor)
  // Оба ряда имеют одинаковый нейтральный фон (background.paper) — зелёного нет ни у одного.
  expect(acceptedBg).toBe(blockedBg)
  expect(acceptedBg).toBe('rgb(255, 255, 255)')
  expect(acceptedBorder).toBe('rgba(0, 0, 0, 0)')
  expect(blockedBorder).toBe('rgba(0, 0, 0, 0)')
  const deliver = page.getByRole('button', { name: 'Передать в WB' })
  await expect(deliver).toBeDisabled()
  await deliver.hover()
  await expect(page.getByRole('tooltip')).toContainText('Заказ №2: WB не принял: неверный статус УИН')
})

// S-03-TC-014 — an accepted WB verdict stays in the chip while row colors show only scanner/print state.
test('fbs workspace: accepted verdict does not paint order rows green', async ({ page }) => {
  const accepted = order('1', {
    supply_id: 'sup-1',
    sticker: { status: 'pending', asset_url: null, applied_at: null },
    metadata: {
      required: ['sgtin'],
      optional: [],
      states: [{ kind: 'sgtin', status: 'accepted', value_tail: '…5678' }],
      delivery_allowed: true,
      verdict: { signature: 'WB: принято', tone: 'ok', reason: null, delivery_allowed: true },
      last_checked_at: new Date().toISOString(),
    },
  })
  const printed = order('2', { supply_id: 'sup-1' })
  const scannerActive = order('3', {
    supply_id: 'sup-1',
    sticker: { status: 'pending', asset_url: null, applied_at: null },
  })
  await openVerdictWorkspace(page, 'verdict-row-colors', [accepted, printed, scannerActive])
  await page.route('**/operations/fbs-orders/kiz/lookup**', (route) =>
    json(route, {
      order_id: '3',
      wb_order_id: 3,
      product: {
        name: 'Товар 3',
        image_url: null,
        barcode: '2000003',
        seller_article: 'ART-3',
      },
      current_kiz: null,
      needs_confirmation: false,
      can_bind: true,
      block_reason: null,
    }),
  )

  const scanInput = page.getByTestId('fbs-kiz-scan-input')
  await scanInput.fill('WB0000000003')
  await scanInput.press('Enter')
  await expect(page.getByTestId('fbs-kiz-row-active')).toContainText('заказ 3')

  const acceptedChip = page.getByTestId('fbs-wb-verdict-1')
  await expect(acceptedChip).toHaveText('WB: принято')
  expect(await acceptedChip.evaluate((el) => window.getComputedStyle(el).backgroundColor))
    .toBe('rgba(27, 107, 69, 0.12)')

  const acceptedRow = page.getByTestId('fbs-kiz-row-1')
  const printedRow = page.getByTestId('fbs-kiz-row-2')
  const activeRow = page.getByTestId('fbs-kiz-row-active')
  const acceptedStyle = await acceptedRow.evaluate((el) => {
    const style = window.getComputedStyle(el)
    return { backgroundColor: style.backgroundColor, borderLeftColor: style.borderLeftColor }
  })
  const printedStyle = await printedRow.evaluate((el) => {
    const style = window.getComputedStyle(el)
    return { backgroundColor: style.backgroundColor, borderLeftColor: style.borderLeftColor }
  })
  const activeStyle = await activeRow.evaluate((el) => {
    const style = window.getComputedStyle(el)
    return { backgroundColor: style.backgroundColor, borderLeftColor: style.borderLeftColor }
  })

  expect(acceptedStyle).toEqual({
    backgroundColor: 'rgb(255, 255, 255)',
    borderLeftColor: 'rgba(0, 0, 0, 0)',
  })
  expect(printedStyle).toEqual({
    backgroundColor: 'rgba(0, 0, 0, 0.04)',
    borderLeftColor: 'rgba(0, 0, 0, 0)',
  })
  expect(activeStyle).toEqual({
    backgroundColor: 'rgb(3, 169, 244)',
    borderLeftColor: 'rgb(2, 136, 209)',
  })
  expect(await page.getByTestId('fbs-kiz-tail').first().evaluate((el) => window.getComputedStyle(el).color))
    .toBe('rgb(27, 94, 32)')
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
