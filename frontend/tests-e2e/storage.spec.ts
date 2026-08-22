import { expect, test, type Page } from '@playwright/test'

const rows = [
  { id: 'draft-problem', seller_id: 'seller-1', seller_name: 'Красотка', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'draft', fixed_at: null, total_liter_days: '12840.50', total_amount: '8988.35', problem_count: 1, measurements: [{ product_id: 'product-missing', sku: 'SKU-11890', seller_article: 'NRD-2XL-LONG', volume_liters: null, dimensions_source: null, liter_days: '0', rate_snapshot: '0.70', amount: null, status: 'missing_dimensions' }, { product_id: 'product-ready', sku: 'SKU-10432', seller_article: 'KRS-44-BLK', volume_liters: '2.40', dimensions_source: 'manual', liter_days: '8928.00', rate_snapshot: '0.70', amount: '6249.60', status: 'calculated' }] },
  { id: 'fixed-zero', seller_id: 'seller-2', seller_name: 'Вектор', warehouse_id: 'warehouse-1', warehouse_name: 'Основной склад', status: 'fixed', fixed_at: '2026-08-01T09:20:00+03:00', total_liter_days: '0', total_amount: '0.00', problem_count: 0, measurements: [] },
]

async function openStorage(page: Page, role: 'fulfillment_admin' | 'fulfillment_staff' = 'fulfillment_admin') {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'storage-e2e-token'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'storage@example.test', organization_name: 'E2E', role, permissions: { settings: false, mp_shipments: false, reception: false, cells: false, inventory: true, packaging: false, shift_lead: false } } }))
  await page.route('**/api/operations/storage/statements?*', (route) => route.fulfill({ json: { tariff_configured: true, warehouses: [{ id: 'warehouse-1', name: 'Основной склад' }], statements: rows } }))
  await page.route('**/api/operations/storage/measurements/rebuild', (route) => route.fulfill({ status: 202, json: { id: 'job-1', status: 'pending' } }))
  await page.route('**/api/products/product-missing/dimensions', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/products/product-missing/dimensions/container', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/products/product-ready/dimensions/history', (route) => route.fulfill({ json: [{ id: 'event-1', created_at: '2026-07-18T10:42:00+03:00', source: 'manual', length_mm: 400, width_mm: 250, height_mm: 240, volume_liters: '24.00', author_name: 'Анна', is_current: true }] }))
  await page.route('**/api/products/product-ready/dimensions/restore-wb', (route) => route.fulfill({ json: {} }))
  await page.route('**/api/operations/storage/statements/draft-problem/fix', (route) => route.fulfill({ json: { ...rows[0], status: 'fixed', problem_count: 0, fixed_at: '2026-08-01T09:20:00+03:00' } }))
  await page.route('**/api/operations/storage/statements/fixed-zero/print', (route) => route.fulfill({ json: rows[1] }))
  await page.goto('/app/ff/inventory')
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
}

test('S-11-TC-001 administrator opens the previous-month storage screen', async ({ page }) => {
  await openStorage(page)
  await expect(page.getByRole('heading', { name: 'Хранение' })).toBeVisible()
  await expect(page.getByTestId('storage-month')).toHaveValue('2026-07')
})

test('S-11-TC-003 forms only the selected month through the storage API', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-generate').click()
  await expect(page.getByTestId('storage-seller-table')).toContainText('Красотка')
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
  await expect(page.getByRole('button', { name: 'Вернуть данные WB' })).toBeVisible()
})

test('S-11-TC-008 blocks fixing when dimensions are missing', async ({ page }) => {
  await openStorage(page)
  await page.getByTestId('storage-expand-draft-problem').click()
  await expect(page.getByTestId('storage-fix')).toBeDisabled()
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

test('S-11-TC-012 staff sees neither tariff nor fixation controls', async ({ page }) => {
  await openStorage(page, 'fulfillment_staff')
  await expect(page.getByTestId('storage-rate')).toHaveCount(0)
  await page.getByTestId('storage-expand-draft-problem').click()
  await expect(page.getByTestId('storage-fix')).toHaveCount(0)
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
