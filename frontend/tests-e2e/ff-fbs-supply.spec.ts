import { expect, test, type Page, type Route } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// Component-style UI coverage for screens 2 (карточка отгрузки) and 3 (лист
// подбора). These tests keep isolated route fixtures; real WMS ↔ WB emulator
// coverage lives in the backend integration lane and must not be confused with
// these mocked browser scenarios.

function fbsOrder(id: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id,
    seller_id: 's-1',
    warehouse_id: 'w-1',
    product_id: `p-${id}`,
    wb_order_id: Number(id.replace(/\D/g, '') || '1'),
    wb_rid: `rid-${id}`,
    wb_nm_id: 1000,
    wb_chrt_id: null,
    wb_article: `ART-${id}`,
    wb_barcode: `200000${id}`,
    price: 1990,
    is_legal: false,
    cargo_type: 'mgt',
    wb_office_id: 1,
    can_pvz: true,
    supply_id: null,
    trbx_id: null,
    status: 'new',
    wb_status: 'waiting',
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date(Date.now() + 100 * 3600 * 1000).toISOString(),
    mapping_status: 'mapped',
    reserve_status: 'reserved',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  }
}

function fbsSupply(status: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'sup-1',
    seller_id: 's-1',
    warehouse_id: 'w-1',
    wb_supply_id: 'WB-GI-1',
    name: 'Тестовая отгрузка',
    status,
    delivery_type: 'warehouse_sc',
    cargo_type: 'mgt',
    wb_office_id: 1,
    barcode_file: null,
    document_number: null,
    display_number: null,
    created_at_wb: null,
    delivered_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    orders: [
      { id: 'o-1', wb_order_id: 1, status, supply_id: 'sup-1', trbx_id: null, sticker_code: null, sticker_file: null },
    ],
    ...over,
  }
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

// TC-NEW-FBS-SUPPLYUI-004/005 — передача в доставку через подтверждение.
// Given: упакованная отгрузка (packed); When: открыть карточку, «Передать в доставку», подтвердить;
// Then: вызывается POST /deliver, статус → in_delivery. Negative: отмена диалога не меняет статус.
test('fbs supply: deliver with confirm', async ({ page }) => {
  await registerFf(page, 'deliver')

  let supplyStatus = 'packed'
  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET'
      ? json(r, [fbsOrder('1', { status: 'in_supply', supply_id: 'sup-1' })])
      : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/deliver', async (r) => {
    supplyStatus = 'in_delivery'
    await json(r, fbsSupply('in_delivery'))
  })
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, fbsSupply(supplyStatus)) : r.fallback(),
  )

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-orders-tab-assembly').click()
  await page.getByTestId('fbs-order-row').first().click()
  await expect(page.getByTestId('fbs-supply-drawer')).toBeVisible()
  await expect(page.getByTestId('fbs-supply-stepper')).toBeVisible()

  // Negative: открыть диалог и отменить — статус не меняется, кнопка deliver ещё активна.
  await page.getByTestId('fbs-supply-deliver').click()
  await page.getByTestId('fbs-supply-deliver-cancel').click()
  await expect(page.getByTestId('fbs-supply-deliver')).toBeEnabled()

  // Подтвердить передачу → статус переходит в доставку.
  await page.getByTestId('fbs-supply-deliver').click()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/deliver') && res.request().method() === 'POST'),
    page.getByTestId('fbs-supply-deliver-confirm').click(),
  ])
  await expect(page.locator('[data-testid="fbs-supply-drawer"] [data-status="in_delivery"]').first()).toBeVisible()
})

// TC-NEW-FBS-SUPPLYUI-006 — создание отгрузки из выделенных заказов.
// Given: на вкладке «Новые» выделены 2 заказа одного селлера; When: «Создать отгрузку» → подтвердить;
// Then: POST /fbs-supplies + POST /{id}/orders, открывается карточка отгрузки.
test('fbs supply: create from selected orders', async ({ page }) => {
  await registerFf(page, 'create')

  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET' ? json(r, [fbsOrder('1'), fbsOrder('2')]) : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies', (r) =>
    r.request().method() === 'POST' ? json(r, fbsSupply('draft', { orders: [] }), 201) : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/orders', (r) =>
    r.request().method() === 'POST' ? json(r, fbsSupply('assembling')) : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, fbsSupply('assembling')) : r.fallback(),
  )

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-order-checkbox').first().click()
  await page.getByTestId('fbs-order-checkbox').nth(1).click()
  await expect(page.getByTestId('fbs-orders-action-bar')).toBeVisible()
  await page.getByTestId('fbs-create-supply').click()
  await Promise.all([
    page.waitForResponse(
      (res) => res.url().endsWith('/operations/fbs-supplies') && res.request().method() === 'POST',
    ),
    page.getByTestId('fbs-create-supply-submit').click(),
  ])
  await expect(page.getByTestId('fbs-supply-drawer')).toBeVisible()
})

// TC-NEW-FBS-SUPPLYUI-007 — draft is not silently treated as assembling.
// The operator starts assembly explicitly, receives a packaging task, and can
// hand already printed KIZ codes to WB from the same supply card.
test('fbs supply: start assembly creates packaging task and assigns printed KIZ', async ({ page }) => {
  await registerFf(page, 'start-assembly')

  const draft = fbsSupply('draft', { packaging_task_id: null })
  const assembling = fbsSupply('assembling', { packaging_task_id: 'pack-task-1' })
  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET'
      ? json(r, [fbsOrder('1', { status: 'in_supply', supply_id: 'sup-1' })])
      : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, draft) : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/status', async (r) => {
    expect(r.request().postDataJSON()).toEqual({ status: 'assembling' })
    await json(r, assembling)
  })
  await page.route('**/operations/fbs-orders/supplies/*/markings/assign-printed', async (r) => {
    await json(r, [{ id: 'marking-1', order_id: 'o-1', kind: 'sgtin', value: '0101', check_status: 'ok', marking_code_id: 'code-1' }])
  })

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-orders-tab-assembly').click()
  await page.getByTestId('fbs-order-row').first().click()
  await expect(page.getByTestId('fbs-supply-start-assembly')).toBeVisible()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/status') && res.request().method() === 'PUT'),
    page.getByTestId('fbs-supply-start-assembly').click(),
  ])
  await expect(page.getByTestId('fbs-supply-open-packaging')).toBeVisible()
  await expect(page.getByTestId('fbs-supply-assign-markings')).toBeVisible()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/markings/assign-printed') && res.request().method() === 'POST'),
    page.getByTestId('fbs-supply-assign-markings').click(),
  ])
  await expect(page.getByTestId('fbs-supply-info')).toContainText('КИЗ переданы в WB: 1')
})

// TC-NEW-FBS-PVZUI-001 — operator can assign two real supply orders to a trbx.
test('fbs PVZ supply: bind two orders to trbx with dimensions', async ({ page }) => {
  await registerFf(page, 'pvz-trbx')

  const orders = [
    { id: 'o-1', wb_order_id: 1, status: 'assembling', supply_id: 'sup-1', trbx_id: null, sticker_code: null, sticker_file: null },
    { id: 'o-2', wb_order_id: 2, status: 'assembling', supply_id: 'sup-1', trbx_id: null, sticker_code: null, sticker_file: null },
  ]
  const supply = fbsSupply('assembling', { delivery_type: 'pvz', orders })
  const trbx = {
    id: 'trbx-1',
    wb_trbx_id: 'WB-TRBX-1',
    packaging_box_id: null,
    length_mm: null,
    width_mm: null,
    height_mm: null,
    weight_g: null,
    sticker_file: null,
  }

  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET'
      ? json(r, orders.map((order) => fbsOrder(order.id, order)))
      : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/trbx/stickers', (r) => json(r, { trbxes: [trbx] }))
  await page.route('**/operations/fbs-supplies/*/trbx/*/orders', async (r) => {
    expect(r.request().postDataJSON()).toEqual({
      order_ids: ['o-1', 'o-2'],
      length_mm: 400,
      width_mm: 300,
      height_mm: 200,
      weight_g: 2000,
    })
    await json(r, trbx)
  })
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, supply) : r.fallback(),
  )

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-orders-tab-assembly').click()
  await page.getByTestId('fbs-order-row').first().click()
  await expect(page.getByTestId('fbs-trbx-row')).toBeVisible()

  await page.getByTestId('fbs-trbx-order-trbx-1-o-1').check()
  await page.getByTestId('fbs-trbx-order-trbx-1-o-2').check()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/trbx/trbx-1/orders') && res.request().method() === 'POST'),
    page.getByTestId('fbs-trbx-bind-trbx-1').click(),
  ])
  await expect(page.getByTestId('fbs-trbx-bind-trbx-1')).toBeVisible()
})

// TC-NEW-FBS-PVZUI-002 — create a real WMS physical box (WHB), bind it to a
// WB cargo place, and expose its barcode for reprint/scanning.
test('fbs PVZ supply: create and bind physical WHB box', async ({ page }) => {
  await registerFf(page, 'pvz-box')

  const order = { id: 'o-1', wb_order_id: 1, status: 'assembling', supply_id: 'sup-1', trbx_id: null, sticker_code: null, sticker_file: null }
  const supply = fbsSupply('assembling', { delivery_type: 'pvz', packaging_task_id: 'pack-task-1', orders: [order] })
  const trbx = {
    id: 'trbx-1', wb_trbx_id: 'WB-TRBX-1', packaging_box_id: null, packaging_box_barcode: null,
    length_mm: 400, width_mm: 300, height_mm: 200, weight_g: 2000, sticker_file: null,
  }
  const boundTrbx = { ...trbx, packaging_box_id: 'box-1', packaging_box_barcode: 'WHB-000001' }

  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET' ? json(r, [fbsOrder(order.id, order)]) : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/trbx/stickers', (r) => json(r, { trbxes: [trbx] }))
  let boxRequestCount = 0
  await page.route('**/operations/fbs-supplies/*/trbx/*/box', async (r) => {
    boxRequestCount += 1
    expect(r.request().postDataJSON()).toEqual(
      boxRequestCount === 1 ? { barcode: null } : { barcode: 'WHB-000001' },
    )
    await json(r, boundTrbx)
  })
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, supply) : r.fallback(),
  )

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-orders-tab-assembly').click()
  await page.getByTestId('fbs-order-row').first().click()
  await expect(page.getByTestId('fbs-trbx-row')).toBeVisible()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/trbx/trbx-1/box') && res.request().method() === 'POST'),
    page.getByTestId('fbs-trbx-box-create-trbx-1').click(),
  ])
  await expect(page.getByTestId('fbs-trbx-box-barcode-trbx-1')).toHaveValue('WHB-000001')
  await expect(page.getByTestId('fbs-trbx-box-print-trbx-1')).toBeVisible()
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/trbx/trbx-1/box') && res.request().method() === 'POST'),
    page.getByTestId('fbs-trbx-box-bind-trbx-1').click(),
  ])
  expect(boxRequestCount).toBe(2)
})

// TC-NEW-FBS-PICKUI-001/002 — лист подбора: загрузка, отметка, фильтр.
// Given: отгрузка на сборке; When: открыть лист подбора, отметить «Собрал», включить «Не собраны»;
// Then: позиции видны, счётчик растёт, собранная позиция скрывается фильтром.
test('fbs pick list: load, collect and filter', async ({ page }) => {
  await registerFf(page, 'pick')

  await page.route('**/operations/fbs-orders**', (r) =>
    r.request().method() === 'GET'
      ? json(r, [fbsOrder('1', { status: 'in_supply', supply_id: 'sup-1' })])
      : r.fallback(),
  )
  await page.route('**/operations/fbs-supplies/*/picking-list', (r) =>
    json(r, {
      items: [
        { article: 'ART-1', sku_code: 'SKU1', size: 'M', product_name: 'Товар 1', quantity: 2 },
        { article: 'ART-2', sku_code: 'SKU2', size: null, product_name: 'Товар 2', quantity: 1 },
      ],
    }),
  )
  await page.route('**/operations/fbs-supplies/*', (r) =>
    r.request().method() === 'GET' ? json(r, fbsSupply('assembling')) : r.fallback(),
  )

  await page.goto('/app/ff/fbs')
  await page.getByTestId('fbs-orders-tab-assembly').click()
  await page.getByTestId('fbs-order-row').first().click()
  await page.getByTestId('fbs-supply-open-pick-list').click()

  await expect(page.getByTestId('fbs-pick-list')).toBeVisible()
  await expect(page.getByTestId('fbs-pick-row')).toHaveCount(2)

  // Отметить первую позицию «Собрал».
  await page.getByTestId('fbs-pick-row').first().getByTestId('fbs-pick-collected').click()

  // Фильтр «Не собраны» — собранная позиция скрывается, остаётся одна.
  await page.getByTestId('fbs-pick-filter-not_collected').click()
  await expect(page.getByTestId('fbs-pick-row')).toHaveCount(1)
})
