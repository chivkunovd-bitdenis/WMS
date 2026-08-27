import { expect, test, type Page } from '@playwright/test'

async function authenticate(page: Page, sellers = [{ id: 'seller-1', name: 'Луна' }]) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-seller-report-admin'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ email: 'seller-report@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }) }))
  for (const endpoint of ['warehouses', 'products', 'products/ff-catalog']) {
    await page.route(`**/api/${endpoint}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  }
  await page.route('**/api/sellers', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sellers) }))
}

// TC-NEW-001 — Given a seller report, When finance is off, Then money and invoice history are absent.
test('seller report switches finance shape and renders one storage row', async ({ page }) => {
  await authenticate(page)
  let lastSummary = ''
  await page.route('**/api/billing/seller-report/summary?**', async (route) => {
    lastSummary = route.request().url()
    const finance = new URL(lastSummary).searchParams.get('include_finance') === 'true'
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [{ seller_id: 'seller-1', seller_name: 'Луна', operation_count: 2, item_quantity: 6, not_billable_count: 0, details_target: '/api/billing/seller-report/sellers/seller-1/details', ...(finance ? { unpriced_count: 0, net_total_kopecks: 63000 } : {}) }], totals: { seller_count: 1, operation_count: 2, item_quantity: 6, not_billable_count: 0, ...(finance ? { net_total_kopecks: 63000 } : {}) } }) })
  })
  await page.route('**/api/billing/seller-report/sellers/seller-1/details?**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const finance = requestUrl.searchParams.get('include_finance') === 'true'
    const nextPage = requestUrl.searchParams.get('cursor') === 'cursor-1'
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seller_id: 'seller-1', seller_name: 'Луна', next_cursor: nextPage ? null : 'cursor-1', totals: { operation_count: 2, item_quantity: 6, not_billable_count: 0 }, storage_row: nextPage ? null : { kind: 'storage', date_from: '2026-08-20', date_to: '2026-08-22', liter_days: 18, status: 'calculated', calculation_token: 'opaque', ...(finance ? { amount_kopecks: 500 } : {}) }, entries: [{ id: nextPage ? 'legacy_billing:2' : 'legacy_billing:1', kind: 'legacy_billing', occurred_at: nextPage ? '2026-08-20T09:00:00+03:00' : '2026-08-20T10:00:00+03:00', service_code: 'inbound', item_quantity: 6, source_type: 'inbound_intake', source_id: 'inbound-1', document_number: 'ПР-0001', product_name: 'Платье', sku: 'SKU-1', source_target: { kind: 'inbound', source_id: 'inbound-1' }, result: 'completed', ...(finance ? { unit: 'item', rate_kopecks: 1200, amount_kopecks: 63000, invoice_history: { state: 'known', count: 1 } } : {}) }] }) })
  })
  await page.goto('/app/ff/billing')
  await expect(page.getByRole('tab', { name: 'Селлеры' })).toBeVisible()
  await expect(page.getByTestId('billing-seller-summary')).toContainText('Луна')
  await expect(page.getByRole('columnheader', { name: 'Начислено' })).toHaveCount(0)
  await expect.poll(() => new URL(lastSummary).searchParams.get('include_finance')).toBe('false')
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByTestId('billing-seller-storage')).toContainText('Хранение')
  await expect(page.getByTestId('billing-seller-storage')).toContainText('Рассчитано')
  await expect(page.getByTestId('billing-seller-storage').locator('tbody tr')).toHaveCount(1)
  await expect(page.getByRole('columnheader', { name: 'Документ / источник' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Товар / SKU' })).toBeVisible()
  await expect(page.getByTestId('billing-seller-entries')).toContainText('Выполнено')
  await expect(page.getByRole('columnheader', { name: 'Счёт выставлялся' })).toHaveCount(0)
  await page.getByTestId('billing-seller-finance').click()
  await expect(page.getByRole('columnheader', { name: 'Начислено' })).toBeVisible()
  await expect(page.getByTestId('billing-seller-metrics')).toContainText('630,00 ₽')
  await expect(page.getByTestId('billing-seller-details')).toHaveCount(0)
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByRole('columnheader', { name: 'Счёт выставлялся' })).toBeVisible()
  await expect(page.getByText('✓ 1')).toBeVisible()
  await expect(page.getByTestId('billing-seller-entries').getByRole('checkbox')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Выставить счёт/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Загрузить ещё' }).click()
  await expect(page.getByTestId('billing-seller-entries').locator('tbody tr')).toHaveCount(2)
  await expect(page.getByTestId('billing-seller-storage').locator('tbody tr')).toHaveCount(1)
  await page.reload()
  await expect(page.getByRole('columnheader', { name: 'Начислено' })).toBeVisible()
})

test('seller report ignores a held stale summary and detail response', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/billing/seller-report/summary?**', async (route) => {
    const search = new URL(route.request().url()).searchParams.get('search')
    if (search === 'старый') await new Promise((resolve) => setTimeout(resolve, 350))
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [{ seller_id: 'seller-1', seller_name: search === 'старый' ? 'Старый селлер' : 'Новый селлер', operation_count: 1, item_quantity: 1, not_billable_count: 0, details_target: '/api/billing/seller-report/sellers/seller-1/details' }], totals: { seller_count: 1, operation_count: 1, item_quantity: 1, not_billable_count: 0 } }) })
  })
  await page.route('**/api/billing/seller-report/sellers/seller-1/details?**', async (route) => {
    const finance = new URL(route.request().url()).searchParams.get('include_finance') === 'true'
    if (!finance) await new Promise((resolve) => setTimeout(resolve, 350))
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seller_id: 'seller-1', seller_name: 'Новый селлер', next_cursor: null, totals: { operation_count: 1, item_quantity: 1, not_billable_count: 0 }, storage_row: null, entries: [{ id: finance ? 'new-entry' : 'old-entry', kind: 'legacy_billing', occurred_at: '2026-08-20T10:00:00+03:00', service_code: 'inbound', item_quantity: 1, source_type: 'inbound_intake', source_id: 'inbound-1', document_number: finance ? 'НОВЫЙ-1' : 'СТАРЫЙ-1', product_name: null, sku: null, source_target: { kind: 'inbound', source_id: 'inbound-1' }, result: 'completed', ...(finance ? { unit: 'item', rate_kopecks: 100, amount_kopecks: 100, invoice_history: { state: 'known', count: 0 } } : {}) }] }) })
  })
  await page.goto('/app/ff/billing')
  await page.getByPlaceholder('Селлер').fill('старый')
  await page.getByPlaceholder('Селлер').fill('новый')
  await expect(page.getByTestId('billing-seller-summary')).toContainText('Новый селлер')
  await page.waitForTimeout(450)
  await expect(page.getByTestId('billing-seller-summary')).not.toContainText('Старый селлер')
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await page.getByTestId('billing-seller-finance').click()
  await expect(page.getByTestId('billing-seller-details')).toHaveCount(0)
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByTestId('billing-seller-entries')).toContainText('НОВЫЙ-1')
  await page.waitForTimeout(450)
  await expect(page.getByTestId('billing-seller-entries')).not.toContainText('СТАРЫЙ-1')
})

test('seller report clears Luna details when the seller or period becomes empty', async ({ page }) => {
  await authenticate(page, [{ id: 'seller-1', name: 'Луна' }, { id: 'seller-empty', name: 'Пустой селлер' }])
  await page.route('**/api/billing/seller-report/summary?**', async (route) => {
    const url = new URL(route.request().url())
    const isEmpty = url.searchParams.get('seller_id') === 'seller-empty' || url.searchParams.get('date_from') !== url.searchParams.get('date_to')
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(isEmpty
      ? { rows: [], totals: { seller_count: 0, operation_count: 0, item_quantity: 0, not_billable_count: 0 } }
      : { rows: [{ seller_id: 'seller-1', seller_name: 'Луна', operation_count: 1, item_quantity: 1, not_billable_count: 0, details_target: '/api/billing/seller-report/sellers/seller-1/details' }], totals: { seller_count: 1, operation_count: 1, item_quantity: 1, not_billable_count: 0 } }) })
  })
  await page.route('**/api/billing/seller-report/sellers/seller-1/details?**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ seller_id: 'seller-1', seller_name: 'Луна', next_cursor: null, totals: { operation_count: 1, item_quantity: 1, not_billable_count: 0 }, storage_row: { kind: 'storage', date_from: '2026-08-20', date_to: '2026-08-20', liter_days: 3, status: 'calculated', calculation_token: 'opaque' }, entries: [{ id: 'legacy_billing:luna', kind: 'legacy_billing', occurred_at: '2026-08-20T10:00:00+03:00', service_code: 'inbound', item_quantity: 1, source_type: 'inbound_intake', source_id: 'inbound-1', document_number: 'ЛУНА-1', product_name: null, sku: null, source_target: { kind: 'inbound', source_id: 'inbound-1' }, result: 'completed' }] }),
  }))

  await page.goto('/app/ff/billing')
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByTestId('billing-seller-details')).toContainText('ЛУНА-1')
  await expect(page.getByTestId('billing-seller-storage')).toContainText('Хранение')

  await page.getByLabel('Селлер').selectOption('seller-empty')
  await expect(page.getByTestId('billing-seller-summary')).toContainText('За выбранный период операций нет')
  await expect(page.getByTestId('billing-seller-details')).toHaveCount(0)

  await page.getByLabel('Селлер').selectOption('all')
  await expect(page.getByRole('button', { name: 'Показать операции' })).toBeVisible()
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByTestId('billing-seller-details')).toContainText('ЛУНА-1')
  await page.getByRole('button', { name: '7 дней' }).click()
  await expect(page.getByTestId('billing-seller-summary')).toContainText('За выбранный период операций нет')
  await expect(page.getByTestId('billing-seller-details')).toHaveCount(0)
})
