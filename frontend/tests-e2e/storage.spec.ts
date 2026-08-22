import { expect, test, type Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

const rows = [
  { id: 'draft-problem', seller_id: 'seller-1', seller_name: 'Красотка', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'draft', fixed_at: null, total_liter_days: '12840.50', total_amount: '8988.35', problem_count: 1, measurements: [{ product_id: 'product-missing', sku: 'SKU-11890', seller_article: 'NRD-2XL-LONG', volume_liters: null, dimensions_source: null, liter_days: '0', rate_snapshot: '0.70', amount: null, status: 'missing_dimensions' }, { product_id: 'product-ready', sku: 'SKU-10432', seller_article: 'KRS-44-BLK', volume_liters: '2.40', dimensions_source: 'manual', liter_days: '8928.00', rate_snapshot: '0.70', amount: '6249.60', status: 'calculated' }] },
  { id: 'draft-ready', seller_id: 'seller-3', seller_name: 'Норд', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'draft', fixed_at: null, total_liter_days: '6432.00', total_amount: '4502.40', problem_count: 0, measurements: [{ product_id: 'product-nord', sku: 'SKU-20001', seller_article: 'NRD-READY', volume_liters: '1.20', dimensions_source: 'wildberries', liter_days: '6432.00', rate_snapshot: '0.70', amount: '4502.40', status: 'calculated' }] },
  { id: 'fixed-zero', seller_id: 'seller-2', seller_name: 'Вектор', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'fixed', fixed_at: '2026-08-01T09:20:00+03:00', total_liter_days: '0', total_amount: '0.00', problem_count: 0, measurements: [] },
]

async function openStorage(page: Page, role: 'fulfillment_admin' | 'fulfillment_staff' = 'fulfillment_admin', tariffConfigured = true) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'storage-e2e-token'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'storage@example.test', organization_name: 'E2E', role, permissions: { settings: false, mp_shipments: false, reception: false, cells: false, inventory: true, packaging: false, shift_lead: false } } }))
  await page.route('**/api/operations/storage/statements?*', (route) => route.fulfill({ json: { tariff_configured: tariffConfigured, warehouses: [{ id: 'warehouse-1', name: 'Основной склад' }], statements: tariffConfigured ? rows : [] } }))
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

test('S-11-TC-002 administrator saves a future warehouse rate and seller exception in one request', async ({ page }) => {
  const suffix = Date.now()
  const email = `storage-${suffix}@example.com`
  const moscowToday = moscowDate()
  const validFrom = moscowDate(1)
  const currentMonth = moscowToday.slice(0, 7)

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`Storage ${suffix}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  const [registration] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await registration.json()) as { access_token: string }).access_token)
  const headers = { Authorization: `Bearer ${token}` }
  const warehouseResponse = await page.request.post('/api/warehouses', {
    headers,
    data: { name: 'Основной склад', code: `storage-${suffix}` },
  })
  expect(warehouseResponse.ok()).toBeTruthy()
  const warehouseId = String(((await warehouseResponse.json()) as { id: string }).id)
  const sellerResponse = await page.request.post('/api/sellers', { headers, data: { name: 'Красотка' } })
  expect(sellerResponse.ok()).toBeTruthy()
  const sellerId = String(((await sellerResponse.json()) as { id: string }).id)
  const initialTariff = await page.request.post('/api/operations/storage/tariffs', {
    headers,
    data: { warehouse_id: warehouseId, amount: 0.5, valid_from: moscowToday },
  })
  expect(initialTariff.status()).toBe(201)
  const initialRebuild = await page.request.post('/api/operations/storage/measurements/rebuild', {
    headers,
    data: { year: Number(currentMonth.slice(0, 4)), month: Number(currentMonth.slice(5, 7)), warehouse_id: warehouseId },
  })
  expect(initialRebuild.status()).toBe(202)
  await waitForLiveJob(page, headers, String(((await initialRebuild.json()) as { id: string }).id))

  await page.goto('/app/ff/inventory')
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'GET' && response.url().includes('/api/operations/storage/statements?') && response.ok()),
    page.getByTestId('storage-month').fill(currentMonth),
  ])
  await expect(page.getByTestId('storage-seller-table')).toContainText('Красотка')

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

  await page.getByTestId('storage-rate').click()
  await expect(page.getByTestId('storage-rate-valid-from')).toHaveValue(moscowToday)
  await page.getByTestId('storage-rate-amount').fill('0,70')
  await page.getByTestId('storage-rate-valid-from').fill('2000-01-01')
  await expect(page.getByTestId('storage-rate-save')).toBeDisabled()
  await page.getByTestId('storage-rate-valid-from').fill(validFrom)
  await page.getByText('Индивидуальная ставка селлера', { exact: true }).click()
  await page.getByLabel('Селлер').click()
  await page.getByRole('option', { name: 'Красотка' }).click()
  await page.getByLabel('Ставка, ₽/л·день').nth(1).fill('0,65')
  await page.getByLabel('Дата начала').nth(1).fill(validFrom)
  const [tariffResponse] = await Promise.all([
    waitForPostOk(page, '/api/operations/storage/tariffs'),
    waitForPostOk(page, '/api/operations/storage/measurements/rebuild'),
    page.getByTestId('storage-rate-save').click(),
  ])
  expect(tariffResponse.status()).toBe(201)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByTestId('storage-generate')).toBeEnabled()
  expect(tariffPosts).toBe(1)
  expect(rebuildPosts).toBe(1)
  expect(tariffBody).toEqual({
    warehouse_id: warehouseId,
    amount: 0.7,
    valid_from: validFrom,
    seller_exception: { seller_id: sellerId, amount: 0.65, valid_from: validFrom },
  })
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
