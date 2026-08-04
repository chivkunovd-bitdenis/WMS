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

function worklist(items: FbsWorklistFixture[]) {
  return { items, next_cursor: null, server_now: new Date().toISOString() }
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
    const statusGroup = new URL(route.request().url()).searchParams.get('status_group')
    const body = statusGroup === 'new' ? worklist([order('1'), order('2')]) : worklist([])
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.getByTestId('nav-ff-fbs').click()
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toBeVisible()

  await page.getByRole('tab', { name: 'В доставке' }).click()
  await expect(page.getByText('Заказов в этой группе нет')).toBeVisible()
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
  await page.getByLabel('Селлер').click()
  await page.getByRole('option', { name: 'Селлер Один' }).click()
  await expect(page.getByTestId('fbs-order-1')).toBeVisible()
  await expect(page.getByTestId('fbs-order-2')).toHaveCount(0)
})
