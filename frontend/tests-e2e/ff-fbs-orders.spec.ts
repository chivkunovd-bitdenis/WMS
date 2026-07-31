import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// Экран FBS ходит в реальный backend-эндпоинт GET /operations/fbs-orders (реализован задачей
// fbs-orders-intake). Эндпоинт отдаёт список заказов без серверной фильтрации по вкладкам —
// группировку по статусам делает клиент. В тесте мокаем этот GET через page.route и проверяем
// ВИДИМЫЙ результат (вкладки, строки, пустое состояние, фильтр по селлеру).

type FbsOrderFixture = Record<string, unknown>

function order(id: string, over: Partial<FbsOrderFixture> = {}): FbsOrderFixture {
  return {
    id,
    seller_id: 's-1',
    warehouse_id: 'w-1',
    product_id: `p-${id}`,
    wb_order_id: Number(id.replace(/\D/g, '') || '1'),
    wb_rid: `rid-${id}`,
    wb_nm_id: 1000 + Number(id.replace(/\D/g, '') || '1'),
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

// TC-NEW-FBS-FE-001 — список заказов FBS и вкладки статусов (группировка на клиенте).
// Given: оператор ФФ, есть новые заказы; When: открывает FBS и переключает вкладки;
// Then: во «Новых» видит заказы, в пустой вкладке — заглушку empty, а не пустую таблицу.
test('fbs orders: list, tabs and empty state', async ({ page }) => {
  await registerFf(page, 'list')

  await page.route('**/operations/fbs-orders**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const body = [order('1'), order('2')] // оба со статусом new
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })

  await page.goto('/app/ff/fbs')
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-orders-tab-new')).toBeVisible()

  // «Новые» — две строки.
  await expect(page.getByTestId('fbs-order-row')).toHaveCount(2)

  // «В доставке» — среди заказов таких статусов нет → дружелюбная заглушка, не пустая таблица.
  await page.getByTestId('fbs-orders-tab-delivery').click()
  await expect(page.getByTestId('fbs-orders-empty')).toBeVisible()
  await expect(page.getByTestId('fbs-order-row')).toHaveCount(0)
})

// TC-NEW-FBS-FE-002 — фильтр по селлеру (мультиселлер).
// Given: заказы нескольких селлеров; When: оператор выбирает селлера в фильтре;
// Then: запрос уходит с seller_id и в списке остаются заказы только этого селлера.
test('fbs orders: filter by seller', async ({ page }) => {
  await registerFf(page, 'seller')

  // Сидим двух селлеров через реальный API — они попадут в фильтр (после перезагрузки экрана).
  const token = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${token}` }
  const s1 = (await (
    await page.request.post('/api/sellers', { headers: h, data: { name: 'Селлер Один' } })
  ).json()) as { id: string }
  await page.request.post('/api/sellers', { headers: h, data: { name: 'Селлер Два' } })

  await page.route('**/operations/fbs-orders**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const url = new URL(route.request().url())
    const sellerId = url.searchParams.get('seller_id')
    const rows =
      sellerId === s1.id
        ? [order('1', { seller_id: s1.id })]
        : [order('1', { seller_id: s1.id }), order('2', { seller_id: 's-2' })]
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(rows) })
  })

  await page.goto('/app/ff/fbs')
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-row')).toHaveCount(2)

  // Выбираем первого селлера — список сужается до одного заказа.
  await page.getByTestId('fbs-seller-filter').click()
  await page.getByRole('option', { name: 'Селлер Один' }).click()
  await expect(page.getByTestId('fbs-order-row')).toHaveCount(1)
})
