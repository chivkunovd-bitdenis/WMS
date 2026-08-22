import { expect, test, type Page } from '@playwright/test'

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

test('S-11-TC-001 administrator opens the previous-month storage screen', async ({ page }) => {
  await openStorage(page)
  await expect(page.getByRole('heading', { name: 'Хранение' })).toBeVisible()
  await expect(page.getByTestId('storage-month')).toHaveValue('2026-07')
})

test('S-11-TC-002 administrator saves a warehouse storage rate effective forward', async ({ page }) => {
  await openStorage(page, 'fulfillment_admin', false)
  let tariffBody: unknown = null
  await page.route('**/api/operations/storage/tariffs', async (route) => {
    tariffBody = route.request().postDataJSON()
    await route.fulfill({ status: 201, json: { warehouse_tariff: { id: 'tariff-1', warehouse_id: 'warehouse-1', seller_id: null, amount: '0.70', valid_from: '2026-08-01' }, seller_exception: null } })
  })
  await page.getByRole('button', { name: 'Задать тариф' }).click()
  await page.getByTestId('storage-rate-amount').fill('0,70')
  await page.getByTestId('storage-rate-valid-from').fill('2026-08-01')
  await page.getByTestId('storage-rate-save').click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(tariffBody).toEqual({ warehouse_id: 'warehouse-1', amount: 0.7, valid_from: '2026-08-01' })
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
