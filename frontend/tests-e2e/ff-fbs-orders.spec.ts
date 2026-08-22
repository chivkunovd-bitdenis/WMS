import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// Это контрактный browser-test: он мокаeт только FBS worklist, а не выдаёт себя за real-stack.
// Реальный браузерный путь с PostgreSQL, backend и WB emulator — отдельный release gate.

type FbsWorklistFixture = Record<string, unknown>

function order(id: string, over: Partial<FbsWorklistFixture> = {}): FbsWorklistFixture {
  return {
    id,
    seller: { id: 's-1', name: 'Селлер Один' },
    wb_warehouse: { id: 501001, name: 'WB Подольск' },
    wms_warehouse: { id: 'w-1', name: 'Основной склад' },
    wb_order_id: Number(id.replace(/\D/g, '') || '1'),
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
    inventory: { available_unpacked: 3, locations: [{ id: 'loc-1', code: 'A-01', available_unpacked: 3 }] },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: true,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    status: 'new',
    wb_status: 'waiting',
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
    supply_id: null,
    selection_blockers: [],
    ...over,
  }
}

function worklist(items: FbsWorklistFixture[], warehouseOptions: FbsWorklistFixture[] = []) {
  return {
    items,
    next_cursor: null,
    server_now: new Date().toISOString(),
    warehouse_options: warehouseOptions,
  }
}

function wbVerdict(signature: string, over: Record<string, unknown> = {}) {
  return {
    required: [],
    optional: [],
    states: [],
    delivery_allowed: signature === 'WB: принято' || signature === 'WB: код не требуется',
    last_checked_at: new Date().toISOString(),
    verdict: { signature, tone: 'stop', reason: null, delivery_allowed: false, ...over },
  }
}

function supplyRow(id: string, over: Partial<FbsWorklistFixture> = {}): FbsWorklistFixture {
  return {
    id,
    wb_supply_id: `WB-GI-${id}`,
    name: `Поставка ${id}`,
    status: 'assembling',
    seller: { id: 's-1', name: 'Селлер Один' },
    wb_warehouse: { id: 501001, name: 'WB Подольск' },
    wms_warehouse: { id: 'w-1', name: 'Основной склад' },
    orders_count: 2,
    units_count: 2,
    boxes_count: 1,
    planned_shipment_date: '2026-08-16',
    can_add_orders: true,
    ...over,
  }
}

function supplyWorklist(items: FbsWorklistFixture[]) {
  return { items, server_now: new Date().toISOString() }
}

function workspace(items: FbsWorklistFixture[]) {
  return {
    supply: {
      id: 'sup-1',
      wb_supply_id: 'WB-GI-MOCK-1',
      name: 'Тестовая поставка',
      status: 'assembling',
      delivery_type: 'warehouse_sc',
      seller: { id: 's-1', name: 'Селлер Один' },
      wb_warehouse: { id: 501001, name: 'WB Подольск' },
      wms_warehouse: { id: 'w-1', name: 'Основной склад' },
      planned_destination: null,
      nearest_deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
      packaging_task_id: null,
      barcode_asset: null,
    },
    stage: 'picking',
    progress: {
      picked: 0,
      packed: 0,
      metadata_ready: items.length,
      stickers_ready: items.length,
      total: items.length,
    },
    blockers: [],
    orders: items,
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: new Date().toISOString(),
    tracking_summary: null,
    partial_rejection: null,
    wb_sync_stale: false,
  }
}

async function registerFf(page: import('@playwright/test').Page, tag: string) {
  const email = `e2e-fbs-${tag}-${Date.now()}@example.com`
  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`E2E FBS ${tag}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  await expect(page.getByTestId('dashboard')).toBeVisible()
}

// TC-S17-001 / TC-S17-006 — canonical worklist and selection-to-supply browser contract.
test('fbs orders: list, tabs and empty state', async ({ page }) => {
  await registerFf(page, 'list')

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const params = new URL(route.request().url()).searchParams
    const statusGroup = params.get('status_group')
    if (statusGroup === 'new') expect(params.get('limit')).toBe('500')
    const body = statusGroup === 'new'
      ? worklist([order('1'), order('2')])
      : statusGroup === 'cancelled'
        ? worklist([order('5', { status: 'cancelled', wb_status: 'canceled' })])
        : worklist([])
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.route('**/operations/fbs-supplies/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const statusGroup = new URL(route.request().url()).searchParams.get('status_group')
    const body = statusGroup === 'delivery'
      ? supplyWorklist([supplyRow('sup-3', { status: 'in_delivery' })])
      : statusGroup === 'done'
        ? supplyWorklist([supplyRow('sup-4', { status: 'done' })])
        : supplyWorklist([])
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  await page.getByRole('tab', { name: 'В работе' }).click()
  await expect(page.getByText('Поставок в работе нет')).toBeVisible()

  await page.getByRole('tab', { name: 'В доставке' }).click()
  await expect(page.getByTestId('fbs-18-supply-sup-3')).toBeVisible()

  await page.getByRole('tab', { name: 'Завершённые' }).click()
  await expect(page.getByTestId('fbs-18-supply-sup-4')).toBeVisible()

  await page.getByRole('tab', { name: 'Отменённые' }).click()
  await expect(page.getByTestId('fbs-order-5')).toBeVisible()
})

// S-03-TC-001, S-03-TC-002, S-03-TC-003, S-03-TC-006 — WB verdicts stay in the existing status cell.
test('fbs orders: shows the server WB verdict and safe operator reason', async ({ page }) => {
  await registerFf(page, 'wb-verdict')
  const items = [
    order('1', { metadata: wbVerdict('WB: принято', { tone: 'ok', delivery_allowed: true }) }),
    order('2', { metadata: wbVerdict('WB: код не требуется', { tone: 'neutral', delivery_allowed: true }) }),
    order('3', {
      metadata: wbVerdict('WB не принял', {
        tone: 'stop',
        reason: 'invalid_code',
        delivery_allowed: false,
      }),
    }),
    order('4', { metadata: { ...wbVerdict('unknown'), verdict: null } }),
  ]

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const statusGroup = new URL(route.request().url()).searchParams.get('status_group')
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(statusGroup === 'expired' ? worklist(items) : worklist([])),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByRole('tab', { name: 'Просрочены' }).click()

  await expect(page.getByTestId('fbs-order-1-wb-verdict')).toHaveText('WB: принято')
  await expect(page.getByTestId('fbs-order-2-wb-verdict')).toHaveText('WB: код не требуется')
  await expect(page.getByTestId('fbs-order-3-wb-verdict')).toHaveText('WB не принял')
  await expect(page.getByTestId('fbs-order-3')).toContainText('Код маркировки не принят')
  await expect(page.getByTestId('fbs-order-4-wb-verdict')).toHaveText('Нет ответа WB')
  await expect(page.getByTestId('fbs-order-4')).toContainText('Сдача пока недоступна')
  await expect(page.getByTestId('fbs-order-3')).not.toContainText('invalid_code')
})

// S-03-TC-006 — a packed supply without order-level verdict data must not claim readiness.
test('fbs supplies: packed status does not promise delivery', async ({ page }) => {
  await registerFf(page, 'packed-supply-status')

  await page.route('**/operations/fbs-supplies/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(supplyWorklist([supplyRow('sup-packed', { status: 'packed' })])),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByRole('tab', { name: 'В работе' }).click()
  const status = page.getByTestId('fbs-18-supply-status')
  await expect(status).toHaveText('Упакована')
  await expect(status).not.toHaveText('Готова к сдаче')
})

// HOTFIX 20.08.2026: оператор видит полный список и может отметить любые отдельные
// заказы; memo-строки не заставляют React заново строить остальные 499 строк.
test('fbs orders: 500 new orders allow selecting any two orders', async ({ page }) => {
  await registerFf(page, 'five-hundred-orders')
  const allOrders = Array.from({ length: 500 }, (_, index) => order(String(index + 1)))

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const params = new URL(route.request().url()).searchParams
    expect(params.get('status_group')).toBe('new')
    expect(params.get('limit')).toBe('500')
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(worklist(allOrders)),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-order-500')).toBeAttached()
  await page.getByTestId('fbs-order-1').getByRole('checkbox').click()
  await page.getByTestId('fbs-order-500').getByRole('checkbox').click()
  await expect(page.getByTestId('fbs-selection-bar')).toContainText('Выбрано заказов: 2')
  await expect(page.getByRole('button', { name: 'Сформировать поставку' })).toBeEnabled()
})

// TC-FBS-FE-002 — seller_id передаётся в canonical worklist и меняет строки ответа.
test('fbs orders: filter by seller', async ({ page }) => {
  await registerFf(page, 'seller')

  // Создаём селлеров через штатный UI: SellersScreen после каждого POST обновляет общий список
  // в App, поэтому FBS-фильтр получает актуальные options без жёсткой перезагрузки страницы.
  await page.getByTestId('nav-sellers').click()
  await page.getByTestId('seller-name').fill('Селлер Один')
  await page.getByTestId('seller-email').fill(`seller-one-${Date.now()}@example.com`)
  const [sellerOneResponse] = await Promise.all([
    waitForPostOk(page, '/api/sellers/with-account'),
    page.getByTestId('seller-submit').click(),
  ])
  const s1 = (await sellerOneResponse.json()) as { seller_id: string }

  await page.getByTestId('seller-name').fill('Селлер Два')
  await page.getByTestId('seller-email').fill(`seller-two-${Date.now()}@example.com`)
  await Promise.all([
    waitForPostOk(page, '/api/sellers/with-account'),
    page.getByTestId('seller-submit').click(),
  ])

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const url = new URL(route.request().url())
    const sellerId = url.searchParams.get('seller_id')
    const items =
      sellerId === s1.seller_id
        ? [order('1', { seller: { id: s1.seller_id, name: 'Селлер Один' } })]
        : [order('1', { seller: { id: s1.seller_id, name: 'Селлер Один' } }), order('2', { seller: { id: 's-2', name: 'Селлер Два' } })]
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(worklist(items)) })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  // Выбираем первого селлера — список сужается до одного заказа.
  await page.getByRole('combobox', { name: 'Селлер', exact: true }).click()
  await page.getByRole('option', { name: 'Селлер Один' }).click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toHaveCount(0)
})

// TC-NEW-FBS-EXTERNAL-SUPPLY — WB-confirmed orders without local supply are explained outside the supply table.
test('fbs orders: active supplies table explains external WB supply without local card', async ({ page }) => {
  await registerFf(page, 'external-supply')

  const localOrder = order('1', {
    status: 'assembling',
    wb_status: 'confirm',
    supply_id: 'sup-1',
  })
  const externalOrder = order('2', {
    status: 'assembling',
    wb_status: 'confirm',
    supply_id: null,
  })
  let workspaceRequests = 0

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const statusGroup = new URL(route.request().url()).searchParams.get('status_group')
    const body = statusGroup === 'active' ? worklist([localOrder, externalOrder]) : worklist([])
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.route('**/operations/fbs-supplies/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(supplyWorklist([supplyRow('sup-1')])),
    })
  })
  await page.route('**/operations/fbs-supplies/sup-1/workspace', async (route) => {
    workspaceRequests += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(workspace([localOrder])),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByRole('tab', { name: 'В работе' }).click()

  await expect(page.getByTestId('fbs-18-supplies-table')).toBeVisible()
  await expect(page.getByTestId('fbs-18-supply-sup-1')).toBeVisible()
  await expect(page.getByTestId('fbs-06-external-supply-explanation')).toContainText('локальной карточки поставки в WMS нет')

  await expect(page.getByTestId('fbs-order-2')).toHaveCount(0)
  await expect(page.getByTestId('fbs-workspace')).toHaveCount(0)
  expect(workspaceRequests).toBe(0)

  await page.getByTestId('fbs-18-supply-sup-1').click()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  expect(workspaceRequests).toBe(1)
})

// TC-NEW-FBS-05-001 — selected new orders can be added to a compatible existing supply.
test('fbs orders: add selected new orders to existing supply', async ({ page }) => {
  await registerFf(page, 'add-existing')
  const selectedOrders = [order('1'), order('2')]
  let addBody: FbsWorklistFixture | null = null

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(worklist(selectedOrders)),
    })
  })
  await page.route('**/operations/fbs-supplies/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(supplyWorklist([supplyRow('sup-1')])),
    })
  })
  await page.route('**/operations/fbs-supplies/sup-1/orders/batch', async (route) => {
    addBody = route.request().postDataJSON() as FbsWorklistFixture
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(workspace(selectedOrders.map((item) => ({ ...item, supply_id: 'sup-1' })))),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await page.getByTestId('fbs-order-1').getByRole('checkbox').click()
  await page.getByTestId('fbs-order-2').getByRole('checkbox').click()
  await page.getByTestId('fbs-05-add-existing-open').click()
  await page.getByTestId('fbs-05-existing-supply-select').click()
  await page.getByRole('option', { name: /Поставка sup-1/ }).click()
  await page.getByTestId('fbs-05-add-existing-submit').click()

  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  expect(addBody?.order_ids).toEqual(['1', '2'])
  expect(addBody?.idempotency_key).toEqual(expect.any(String))
})

// TC-S17-025 — new-tab worklist is filtered by seller warehouse via API.
test('fbs orders: filter new orders by warehouse', async ({ page }) => {
  await registerFf(page, 'warehouse')

  await page.getByTestId('nav-sellers').click()
  await page.getByTestId('seller-name').fill('ИП Иванова')
  await page.getByTestId('seller-email').fill(`seller-warehouse-${Date.now()}@example.com`)
  const [sellerResponse] = await Promise.all([
    waitForPostOk(page, '/api/sellers/with-account'),
    page.getByTestId('seller-submit').click(),
  ])
  const sellerId = ((await sellerResponse.json()) as { seller_id: string }).seller_id

  const warehouseOptions = [
    { id: '501001', name: 'WB Подольск', wb_warehouse: { id: 501001, name: 'WB Подольск' } },
    { id: '501002', name: 'WB Казань', wb_warehouse: { id: 501002, name: 'WB Казань' } },
  ]
  const orderOne = order('1', {
    wms_warehouse: { id: 'w-1', name: 'WH Юг' },
    wb_warehouse: { id: 501001, name: 'WB Юг' },
  })
  const orderTwo = order('2', {
    wms_warehouse: { id: 'w-2', name: 'WH Север' },
    wb_warehouse: { id: 501002, name: 'WB Север' },
  })
  let lastWbWarehouseId: string | null = null

  await page.route(`**/operations/fbs-sellers/${sellerId}/warehouses`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 501001, name: 'Лосиный парк 1' },
        { id: 501002, name: 'Казань' },
      ]),
    })
  })

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const url = new URL(route.request().url())
    lastWbWarehouseId = url.searchParams.get('wb_warehouse_id')
    const body = lastWbWarehouseId === '501002' ? worklist([orderTwo], warehouseOptions) : worklist([orderOne, orderTwo], warehouseOptions)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  await page.getByRole('combobox', { name: 'Склад селлера / WB' }).click()
  await page.getByRole('option', { name: 'WB Казань' }).click()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toHaveCount(0)
  expect(lastWbWarehouseId).toBe('501002')

  await page.getByRole('combobox', { name: 'Склад селлера / WB' }).click()
  await page.getByRole('option', { name: 'Все склады' }).click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  await page.getByRole('combobox', { name: 'Селлер', exact: true }).click()
  await page.getByRole('option', { name: 'ИП Иванова' }).click()
  await page.getByRole('combobox', { name: 'Склад селлера / WB' }).click()
  await page.getByRole('option', { name: 'Казань' }).click()

  await expect(page.getByTestId('fbs-order-2')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toHaveCount(0)
  expect(lastWbWarehouseId).toBe('501002')
})

// TC-NEW-FBS-SEARCH-001 / TC-NEW-FBS-SELECT-001 / TC-NEW-FBS-EXPORT-001 —
// search highlights without filtering, selection survives search and Excel exports the chosen set.
test('fbs orders: search keeps list, selected drawer stays stable and Excel downloads', async ({ page }) => {
  await registerFf(page, 'search-select-export')

  const bomberOrder = order('1', {
    product: {
      id: 'p-1',
      name: 'Бомбер графитовый',
      image_url: null,
      seller_article: 'BOMBER-1',
      wb_article: 700001,
      barcode: 'BOMBER-BAR',
      sku: 'BOMBER-SKU',
      chrt_id: 771,
      category: 'Бомберы',
      color: 'графит',
      size: 'L',
    },
  })
  const tshirtOrder = order('2', {
    product: {
      id: 'p-2',
      name: 'Футболка белая',
      image_url: null,
      seller_article: 'TSHIRT-2',
      wb_article: 700002,
      barcode: 'TSHIRT-BAR',
      sku: 'TSHIRT-SKU',
      chrt_id: 772,
      category: 'Футболки',
      color: 'белый',
      size: 'M',
    },
  })

  await page.route('**/operations/fbs-orders/worklist**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(worklist([bomberOrder, tshirtOrder])),
    })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  await page.getByTestId('fbs-order-2').getByRole('checkbox').click()
  await expect(page.getByTestId('fbs-selection-bar')).toContainText('Выбрано заказов: 1')

  await page.getByLabel('Поиск: заказ, товар, категория, артикул, ШК, SKU, цвет, размер').fill('бомбер')
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()
  await expect
    .poll(async () => page.getByTestId('fbs-order-1').evaluate((node) => getComputedStyle(node).backgroundColor))
    .toBe('rgba(255, 214, 102, 0.24)')
  await expect(page.getByTestId('fbs-selection-bar')).toContainText('Выбрано заказов: 1')

  await page.getByTestId('fbs-selected-open').click()
  await expect(page.getByTestId('fbs-selected-list')).toContainText('WB №2')
  await expect(page.getByTestId('fbs-selected-list')).toContainText('Футболка белая')
  await page.getByRole('button', { name: 'Закрыть' }).click()

  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('fbs-orders-download-excel').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/fbs-new-orders-\d{4}-\d{2}-\d{2}\.xls/)
})
