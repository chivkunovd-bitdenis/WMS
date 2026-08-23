import { expect, test, type Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  INBOUND_API,
  seedFfSellerInbound,
} from './inbound-boxes-helpers'

const rows = [
  { id: 'draft-problem', seller_id: 'seller-1', seller_name: 'Красотка', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'draft', fixed_at: null, total_liter_days: '12840.50', total_amount: '8988.35', problem_count: 1, measurements: [{ product_id: 'product-missing', sku: 'SKU-11890', seller_article: 'NRD-2XL-LONG', volume_liters: null, dimensions_source: null, liter_days: '0', rate_snapshot: '0.70', amount: null, status: 'missing_dimensions' }, { product_id: 'product-ready', sku: 'SKU-10432', seller_article: 'KRS-44-BLK', volume_liters: '2.40', dimensions_source: 'manual', liter_days: '8928.00', rate_snapshot: '0.70', amount: '6249.60', status: 'calculated' }] },
  { id: 'draft-ready', seller_id: 'seller-3', seller_name: 'Норд', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'draft', fixed_at: null, total_liter_days: '6432.00', total_amount: '4502.40', problem_count: 0, measurements: [{ product_id: 'product-nord', sku: 'SKU-20001', seller_article: 'NRD-READY', volume_liters: '1.20', dimensions_source: 'wildberries', liter_days: '6432.00', rate_snapshot: '0.70', amount: '4502.40', status: 'calculated' }] },
  { id: 'fixed-zero', seller_id: 'seller-2', seller_name: 'Вектор', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'fixed', fixed_at: '2026-08-01T09:20:00+03:00', total_liter_days: '0', total_amount: '0.00', problem_count: 0, measurements: [] },
]

async function openStorage(page: Page, role: 'fulfillment_admin' | 'fulfillment_staff' = 'fulfillment_admin', tariffConfigured = true, statements = tariffConfigured ? rows : []) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'storage-e2e-token'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'storage@example.test', organization_name: 'E2E', role, permissions: { settings: false, mp_shipments: false, reception: false, cells: false, inventory: true, packaging: false, shift_lead: false } } }))
  await page.route('**/api/operations/storage/statements?*', (route) => route.fulfill({ json: { tariff_configured: tariffConfigured, warehouses: [{ id: 'warehouse-1', name: 'Основной склад' }], statements } }))
  await page.route('**/api/operations/storage/measurements/rebuild', (route) => route.fulfill({ status: 202, json: { id: 'job-1', status: 'pending' } }))
  await page.route('**/api/operations/background-jobs/job-1', (route) => route.fulfill({ json: { id: 'job-1', status: 'done', error_message: null } }))
  await page.route('**/api/products/product-missing/dimensions', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/products/product-missing/dimensions/container', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/products/product-ready/dimensions/history', (route) => route.fulfill({ json: [{ id: 'event-1', created_at: '2026-07-18T10:42:00+03:00', source: 'manual', length_mm: 400, width_mm: 250, height_mm: 240, volume_liters: '24.00', author_name: 'Анна', is_current: true }] }))
  await page.route('**/api/products/product-ready/dimensions/restore-wb', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/operations/storage/statements/draft-problem/fix', (route) => route.fulfill({ json: { ...rows[0], status: 'fixed', problem_count: 0, fixed_at: '2026-08-01T09:20:00+03:00' } }))
  await page.route('**/api/operations/storage/statements/draft-ready/fix', (route) => route.fulfill({ json: { ...rows[1], status: 'fixed', fixed_at: '2026-08-01T09:20:00+03:00' } }))
  await page.route('**/api/operations/storage/statements/fixed-zero/print', (route) => route.fulfill({ json: rows[2] }))
  await page.goto('/app/ff/inventory')
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
}

function moscowDate(offsetDays = 0) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(Date.now() + offsetDays * 24 * 60 * 60 * 1000))
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

async function waitForLiveJob(page: Page, headers: Record<string, string>, jobId: string) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await page.request.get(`/api/operations/background-jobs/${jobId}`, { headers })
    expect(response.ok()).toBeTruthy()
    const job = await response.json() as { status: string; error_message?: string | null }
    if (job.status === 'done') return
    expect(job.status, job.error_message ?? 'storage rebuild failed').not.toBe('failed')
    await page.waitForTimeout(50)
  }
  throw new Error('storage rebuild timed out')
}

test('S-11-TC-001 administrator opens the previous-month storage screen', async ({ page }) => {
  await openStorage(page)
  await expect(page.getByRole('heading', { name: 'Хранение' })).toBeVisible()
  await expect(page.getByTestId('storage-month')).toHaveValue('2026-07')
})

test('S-11-TC-002 blocks a rate that rounds to zero before saving', async ({ page }) => {
  await openStorage(page, 'fulfillment_admin', false)
  let tariffPosts = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/operations/storage/tariffs')) tariffPosts += 1
  })

  const setTariff = page.getByRole('button', { name: 'Задать тариф' })
  await expect(setTariff).toBeVisible()
  await setTariff.click()
  await expect(page.getByRole('dialog', { name: 'Тариф хранения' })).toBeVisible()
  const saveRate = page.getByTestId('storage-rate-save')
  await page.getByTestId('storage-rate-amount').fill('0,001')
  await expect(saveRate).toBeDisabled()
  await saveRate.locator('..').hover()
  await expect(page.getByRole('tooltip')).toHaveText('Минимальная сохраняемая ставка — 0,01 ₽/л·день')
  await saveRate.evaluate((button) => (button as HTMLButtonElement).click())
  expect(tariffPosts).toBe(0)
})

test('S-11-TC-018 blocks Moscow-past start dates with a visible explanation', async ({ page }) => {
  await openStorage(page, 'fulfillment_admin', false)
  const moscowToday = moscowDate()
  const yesterday = moscowDate(-1)

  const setTariff = page.getByRole('button', { name: 'Задать тариф' })
  await expect(setTariff).toBeVisible()
  await setTariff.click()
  await expect(page.getByRole('dialog', { name: 'Тариф хранения' })).toBeVisible()
  const saveRate = page.getByTestId('storage-rate-save')
  await page.getByTestId('storage-rate-amount').fill('0,70')

  await page.getByTestId('storage-rate-valid-from').fill(yesterday)
  await expect(saveRate).toBeDisabled()
  await saveRate.locator('..').hover()
  await expect(page.getByRole('tooltip')).toHaveText('Дата начала не может быть в прошлом')

  await page.getByTestId('storage-rate-valid-from').fill(moscowToday)
  await expect(saveRate).toBeEnabled()
})

test('S-11-TC-002 administrator saves a future warehouse rate and seller exception in one request', async ({ page }) => {
  test.setTimeout(120_000)
  const seed = await seedFfSellerInbound(page, `storage-${Date.now()}`)
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  expect(seed.warehouseId).toMatch(uuidPattern)
  expect(seed.sellerId).toMatch(uuidPattern)
  expect(seed.productId).toMatch(uuidPattern)

  const headers = { Authorization: `Bearer ${seed.token}` }
  const moscowToday = moscowDate()
  const yesterday = moscowDate(-1)
  const validFrom = moscowDate(1)
  const currentMonth = moscowToday.slice(0, 7)

  const dimensionsResponse = await page.request.patch(`/api/products/${seed.productId}/dimensions`, {
    headers,
    data: { length_mm: 10_000, width_mm: 10_000, height_mm: 10_000 },
  })
  expect(dimensionsResponse.ok(), await dimensionsResponse.text()).toBeTruthy()

  const inboundId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 1,
  })
  const { boxes } = await beginInboundReceivingWithBoxes(page.request, headers, inboundId, {
    boxCount: 1,
  })
  await fulfillInboundViaBoxScans(page.request, headers, inboundId, boxes, seed.sku, [1])
  const verifyResponse = await page.request.post(`${INBOUND_API}/${inboundId}/verify`, { headers })
  expect(verifyResponse.ok(), await verifyResponse.text()).toBeTruthy()
  const postResponse = await page.request.post(`${INBOUND_API}/${inboundId}/post`, { headers })
  expect(postResponse.ok(), await postResponse.text()).toBeTruthy()

  const initialRebuild = await page.request.post('/api/operations/storage/measurements/rebuild', {
    headers,
    data: { year: Number(currentMonth.slice(0, 4)), month: Number(currentMonth.slice(5, 7)), warehouse_id: seed.warehouseId },
  })
  expect(initialRebuild.status()).toBe(202)
  await waitForLiveJob(page, headers, String(((await initialRebuild.json()) as { id: string }).id))

  const draftResponse = await page.request.get('/api/operations/storage/statements', {
    headers,
    params: {
      year: Number(currentMonth.slice(0, 4)),
      month: Number(currentMonth.slice(5, 7)),
      warehouse_id: seed.warehouseId,
    },
  })
  expect(draftResponse.ok(), await draftResponse.text()).toBeTruthy()
  const draftBody = await draftResponse.json() as {
    tariff_configured: boolean
    statements: Array<{
      id: string
      seller_id: string
      warehouse_id: string
      total_liter_days: string
      total_amount: string
    }>
  }
  expect(draftBody.tariff_configured).toBe(false)
  const draft = draftBody.statements.find((statement) => statement.seller_id === seed.sellerId)
  expect(draft).toBeDefined()
  if (!draft) throw new Error('storage draft was not created for the seeded seller')
  expect(draft.id).toMatch(uuidPattern)
  expect(draft.warehouse_id).toBe(seed.warehouseId)
  expect(Number(draft.total_liter_days)).toBeGreaterThan(0)
  expect(Number(draft.total_amount)).toBe(0)

  await page.goto('/app/ff/inventory')
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'GET' && response.url().includes('/api/operations/storage/statements?') && response.ok()),
    page.getByTestId('storage-month').fill(currentMonth),
  ])
  await expect(page.getByTestId('storage-seller-table')).toContainText('Тариф хранения ещё не задан')

  let tariffPosts = 0
  let rebuildPosts = 0
  let tariffBody: unknown = null
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/operations/storage/tariffs')) {
      tariffPosts += 1
      tariffBody = request.postDataJSON()
    }
    if (request.method() === 'POST' && request.url().includes('/api/operations/storage/measurements/rebuild')) rebuildPosts += 1
  })

  await page.getByRole('button', { name: 'Задать тариф' }).click()
  const warehouseValidFrom = page.getByTestId('storage-rate-valid-from')
  const saveRate = page.getByTestId('storage-rate-save')
  await expect(warehouseValidFrom).toHaveValue(moscowToday)
  await expect(warehouseValidFrom).toHaveAttribute('min', moscowToday)
  await page.getByTestId('storage-rate-amount').fill('0,70')
  await warehouseValidFrom.fill(yesterday)
  await expect(saveRate).toBeDisabled()
  await saveRate.evaluate((button) => (button as HTMLButtonElement).click())
  expect(tariffPosts).toBe(0)
  await warehouseValidFrom.fill(moscowToday)
  await expect(saveRate).toBeEnabled()
  await page.getByText('Индивидуальная ставка селлера', { exact: true }).click()
  await page.getByLabel('Селлер').click()
  await page.getByRole('option', { name: `Box Seller ${seed.suffix}` }).click()
  await page.getByLabel('Ставка, ₽/л·день').nth(1).fill('0,65')
  const sellerValidFrom = page.getByTestId('storage-seller-rate-valid-from')
  await expect(sellerValidFrom).toHaveValue(moscowToday)
  await expect(sellerValidFrom).toHaveAttribute('min', moscowToday)
  await sellerValidFrom.fill(yesterday)
  await expect(saveRate).toBeDisabled()
  await saveRate.evaluate((button) => (button as HTMLButtonElement).click())
  expect(tariffPosts).toBe(0)
  await sellerValidFrom.fill(moscowToday)
  await expect(saveRate).toBeEnabled()
  await warehouseValidFrom.fill(validFrom)
  const [tariffResponse] = await Promise.all([
    waitForPostOk(page, '/api/operations/storage/tariffs'),
    saveRate.click(),
  ])
  expect(tariffResponse.status()).toBe(201)
  const tariffResult = await tariffResponse.json() as {
    warehouse_tariff: { id: string; warehouse_id: string; amount: string; valid_from: string }
    seller_exception: { id: string; seller_id: string; amount: string; valid_from: string } | null
    recalculated_statements: Array<{
      id: string
      total_amount: string
      measurements: Array<{ rate_snapshot: string | null; amount: string | null }>
    }>
  }
  expect(tariffResult.warehouse_tariff.id).toMatch(uuidPattern)
  expect(tariffResult.warehouse_tariff.warehouse_id).toBe(seed.warehouseId)
  expect(tariffResult.seller_exception).not.toBeNull()
  if (!tariffResult.seller_exception) throw new Error('seller exception was not created atomically')
  expect(tariffResult.seller_exception.id).toMatch(uuidPattern)
  expect(tariffResult.seller_exception.seller_id).toBe(seed.sellerId)
  const recalculated = tariffResult.recalculated_statements.find((statement) => statement.id === draft.id)
  expect(recalculated).toBeDefined()
  if (!recalculated) throw new Error('tariff response did not contain the seeded draft')
  const recalculatedMeasurement = recalculated.measurements[0]
  expect(recalculatedMeasurement).toBeDefined()
  if (!recalculatedMeasurement) throw new Error('recalculated draft did not contain a measurement')
  expect(Number(recalculated.total_amount)).toBeGreaterThan(0)
  expect(recalculatedMeasurement.rate_snapshot).toBe('0.65')
  expect(recalculatedMeasurement.amount).not.toBeNull()
  if (recalculatedMeasurement.amount === null) throw new Error('recalculated amount is missing')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByTestId('storage-seller-table')).toContainText(recalculated.total_amount)
  await page.getByTestId(`storage-expand-${draft.id}`).click()
  await expect(page.getByTestId('storage-sku-table')).toContainText('0.65')
  await expect(page.getByTestId('storage-sku-table')).toContainText(recalculatedMeasurement.amount)
  expect(tariffPosts).toBe(1)
  expect(rebuildPosts).toBe(0)
  expect(tariffBody).toEqual({
    warehouse_id: seed.warehouseId,
    amount: 0.7,
    valid_from: validFrom,
    seller_exception: { seller_id: seed.sellerId, amount: 0.65, valid_from: moscowToday },
  })
})

test('S-11-TC-017 tariff repricing failure keeps the last successful summary', async ({ page }) => {
  await openStorage(page)
  let rebuildPosts = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/operations/storage/measurements/rebuild')) rebuildPosts += 1
  })
  await page.route('**/api/operations/storage/tariffs', (route) => route.fulfill({
    status: 500,
    json: { detail: 'storage_recalculation_failed' },
  }))

  await page.getByTestId('storage-rate').click()
  await page.getByTestId('storage-rate-amount').fill('1,40')
  await page.getByTestId('storage-rate-save').click()

  await expect(page.getByRole('dialog')).toContainText('Не удалось сохранить тариф и пересчитать хранение. Последний успешный расчёт сохранён.')
  await expect(page.getByTestId('storage-seller-table')).toContainText('4502.40')
  expect(rebuildPosts).toBe(0)
})

test('S-11-TC-017 keeps the saved tariff dialog open until statement reading recovers', async ({ page }) => {
  await openStorage(page)
  let tariffPosts = 0
  let failRefresh = true

  await page.route('**/api/operations/storage/tariffs', (route) => {
    tariffPosts += 1
    return route.fulfill({ status: 201, json: { recalculated_statements: [rows[1]] } })
  })
  await page.route('**/api/operations/storage/statements?*', (route) => {
    if (failRefresh) return route.fulfill({ status: 500, json: { detail: 'temporary_failure' } })
    return route.fulfill({ json: { tariff_configured: true, warehouses: [{ id: 'warehouse-1', name: 'Основной склад' }], statements: [rows[1]] } })
  })

  await page.getByTestId('storage-rate').click()
  await page.getByTestId('storage-rate-amount').fill('1,40')
  await page.getByTestId('storage-rate-save').click()

  const dialog = page.getByRole('dialog')
  const saveRate = page.getByTestId('storage-rate-save')
  await expect(dialog).toContainText('Тариф сохранён, но расчёты не обновлены')
  await expect(saveRate).toBeDisabled()
  await expect(page.getByTestId('storage-seller-table')).not.toContainText('Красотка')
  await saveRate.evaluate((button) => (button as HTMLButtonElement).click())
  expect(tariffPosts).toBe(1)

  failRefresh = false
  await page.getByTestId('storage-rate-refresh').click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByTestId('storage-seller-table')).toContainText('Норд')
  expect(tariffPosts).toBe(1)
})

test('S-11-TC-003 forms only the selected month through the storage API', async ({ page }) => {
  await openStorage(page)
  let rebuildBody: unknown = null
  let jobPolls = 0
  let summaryLoads = 0
  await page.route('**/api/operations/storage/measurements/rebuild', async (route) => {
    rebuildBody = route.request().postDataJSON()
    await route.fulfill({ status: 202, json: { id: 'job-check', status: 'pending' } })
  })
  await page.route('**/api/operations/background-jobs/job-check', (route) => {
    jobPolls += 1
    return route.fulfill({ json: { id: 'job-check', status: jobPolls === 1 ? 'running' : 'done', error_message: null } })
  })
  await page.route('**/api/operations/storage/statements?*', (route) => {
    summaryLoads += 1
    return route.fulfill({ json: { tariff_configured: true, warehouses: [{ id: 'warehouse-1', name: 'Основной склад' }], statements: [{ ...rows[1], total_liter_days: '7000.00' }] } })
  })
  await page.getByTestId('storage-generate').click()
  await expect(page.getByTestId('storage-seller-table')).toContainText('7000.00')
  expect(rebuildBody).toEqual({ year: 2026, month: 7, warehouse_id: 'warehouse-1' })
  expect(jobPolls).toBe(2)
  expect(summaryLoads).toBe(1)
})

test('S-11-TC-004 expands exactly one seller into SKU rows', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click()
  await expect(page.getByTestId('storage-sku-table')).toContainText('SKU-11890')
})

test('S-11-TC-005 saves a manual measurement through the product API', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click()
  await page.getByRole('button', { name: 'Внести обмер' }).click()
  await page.getByLabel('Длина, см').fill('40'); await page.getByLabel('Ширина, см').fill('28'); await page.getByLabel('Высота, см').fill('12')
  await page.getByRole('button', { name: 'Сохранить' }).click()
})

test('S-11-TC-006 requires a basis for a container-volume measurement', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click(); await page.getByRole('button', { name: 'Внести обмер' }).click()
  await page.getByLabel('Объём тары').check()
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled()
})

test('S-11-TC-007 opens dimension history and lets an administrator restore WB data', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click(); await page.getByTitle('История габаритов').click()
  await expect(page.getByRole('dialog')).toContainText('Анна')
  await expect(page.getByRole('dialog')).toContainText('Ручной обмер')
  await expect(page.getByRole('dialog')).toContainText('Действует')
  await expect(page.getByRole('button', { name: 'Вернуть данные WB' })).toBeVisible()
})

test('S-11-TC-008 fixes a clean statement and opens the A4 preview', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-ready').click()
  await page.getByTestId('storage-fix').click()
  await expect(page.getByTestId('storage-print-preview')).toContainText('Селлер: Норд')
  await expect(page.getByTestId('storage-print-preview')).toContainText('SKU-20001')
  await expect(page.getByTestId('storage-print-preview')).toContainText('Итого: 4502.40 ₽')
})

test('S-11-TC-009 opens a repeat print preview for a fixed document', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-print-fixed-zero').click()
  await expect(page.getByTestId('storage-print-preview')).toContainText('Итого: 0.00 ₽')
})

test('S-11-TC-010 keeps a zero month as a fixed row instead of an empty state', async ({ page }) => {
  await openStorage(page)
  await expect(page.getByTestId('storage-seller-table')).toContainText('Вектор')
  await expect(page.getByTestId('storage-seller-table')).toContainText('0.00')
})

test('S-11-TC-011 searches only the visible summary rows', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('filter-search').fill('SKU-11890')
  await expect(page.getByTestId('storage-seller-table')).toContainText('Красотка')
  await expect(page.getByTestId('storage-seller-table')).not.toContainText('Вектор')
})

test('S-11-TC-012 staff without a tariff sees guidance and no tariff controls', async ({ page }) => {
  await openStorage(page, 'fulfillment_staff', false)
  await expect(page.getByTestId('storage-seller-table')).toContainText('Тариф хранения ещё не задан')
  await expect(page.getByTestId('storage-seller-table')).toContainText('Обратитесь к администратору ФФ')
  await expect(page.getByTestId('storage-rate')).toHaveCount(0)
})

test('S-11-TC-012 staff with a tariff can inspect rows but cannot change or fix billing', async ({ page }) => {
  await openStorage(page, 'fulfillment_staff', true)
  await page.getByTestId('storage-expand-draft-ready').click()
  await expect(page.getByTestId('storage-detail')).toContainText('SKU-20001')
  await expect(page.getByTestId('storage-rate')).toHaveCount(0)
  await expect(page.getByTestId('storage-fix')).toHaveCount(0)
})

test('S-11-TC-012 cells permission alone does not grant access to storage', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'storage-e2e-token'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'storage@example.test', organization_name: 'E2E', role: 'fulfillment_staff', permissions: { settings: false, mp_shipments: false, reception: false, cells: true, inventory: false, packaging: false, shift_lead: false } } }))
  await page.goto('/app/ff/inventory')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await expect(page.getByTestId('ff-storage-page')).toHaveCount(0)
})

test('S-11-TC-013 disables a repeated calculation while one is running', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-generate').click()
  await expect(page.getByTestId('storage-generate')).toBeDisabled()
})

test('S-11-TC-014 rejects invalid dimensions before sending a request', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click(); await page.getByRole('button', { name: 'Внести обмер' }).click()
  await page.getByLabel('Длина, см').fill('-1')
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled()
})

test('S-11-TC-015 closing a measurement dialog does not save it', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click(); await page.getByRole('button', { name: 'Внести обмер' }).click()
  await page.getByRole('button', { name: 'Отмена' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('S-11-TC-017 retains the last summary when a rebuild fails', async ({ page }) => {
  await openStorage(page)
  await page.route('**/api/operations/storage/measurements/rebuild', (route) => route.fulfill({ status: 500 }))
  await page.getByTestId('storage-generate').click()
  await expect(page.getByTestId('storage-seller-table')).toContainText('Красотка')
  await expect(page.getByTestId('storage-error')).toContainText('Последний расчёт сохранён')
})

test('S-11-TC-020 does not show service warehouses in the selector', async ({ page }) => {
  await openStorage(page)
  await expect(page.getByTestId('storage-warehouse')).toHaveCount(0)
})
