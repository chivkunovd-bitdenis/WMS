import { expect, test, type Page } from '@playwright/test'

async function authenticateBillingAdmin(page: Page) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-billing-admin'))
  await page.route('**/api/auth/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ email: 'billing-admin@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }) }))
  for (const endpoint of ['warehouses', 'products', 'products/ff-catalog']) {
    await page.route(`**/api/${endpoint}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  }
  await page.route('**/api/sellers', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 'seller-1', name: 'Луна' }]) }))
}

test.beforeEach(async ({ page }) => authenticateBillingAdmin(page))

// TC-NEW-001 — Given seller aggregates, When the admin opens billing, Then the Sellers tab uses the additive report API.
test('billing sellers keeps server totals and fixed physical columns', async ({ page }) => {
  let summaryUrl = ''
  await page.route('**/api/billing/seller-report/summary?**', async (route) => {
    summaryUrl = route.request().url()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [{ seller_id: 'seller-1', seller_name: 'Луна', operation_count: 3, item_quantity: 12, not_billable_count: 1, details_target: '/api/billing/seller-report/sellers/seller-1/details' }], totals: { seller_count: 1, operation_count: 3, item_quantity: 12, not_billable_count: 1 } }) })
  })
  await page.goto('/app/ff/billing')
  const table = page.getByTestId('billing-seller-summary')
  await expect(page.getByRole('tab', { name: 'Селлеры' })).toBeVisible()
  await expect(table).toContainText('Луна')
  await expect(table.getByRole('columnheader', { name: 'Операций' })).toHaveAttribute('width', '110')
  await expect(table.getByRole('columnheader', { name: 'Штук' })).toHaveAttribute('width', '100')
  await expect(table.getByRole('columnheader', { name: 'Начислено' })).toHaveCount(0)
  await expect.poll(() => new URL(summaryUrl).searchParams.get('include_finance')).toBe('false')
  await expect.poll(() => new URL(summaryUrl).searchParams.has('period')).toBe(false)
})

// TC-NEW-002 — Given finance is enabled, When a seller detail opens, Then only server finance fields and one storage row appear.
test('billing sellers show finance-on detail without a legacy performer view', async ({ page }) => {
  await page.route('**/api/billing/seller-report/summary?**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [{ seller_id: 'seller-1', seller_name: 'Луна', operation_count: 1, item_quantity: 2, not_billable_count: 0, unpriced_count: 0, net_total_kopecks: 1200, details_target: '/api/billing/seller-report/sellers/seller-1/details' }], totals: { seller_count: 1, operation_count: 1, item_quantity: 2, not_billable_count: 0, net_total_kopecks: 1200 } }) }))
  await page.route('**/api/billing/seller-report/sellers/seller-1/details?**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seller_id: 'seller-1', seller_name: 'Луна', next_cursor: null, totals: { operation_count: 1, item_quantity: 2, not_billable_count: 0, net_total_kopecks: 1200 }, storage_row: { kind: 'storage', date_from: '2026-08-20', date_to: '2026-08-22', liter_days: 6, status: 'calculated', amount_kopecks: 300, calculation_token: 'opaque' }, entries: [{ id: 'legacy_billing:1', kind: 'legacy_billing', occurred_at: '2026-08-20T10:00:00+03:00', service_code: 'inbound', item_quantity: 2, source_type: 'inbound_intake', source_id: 'inbound-1', source_target: { kind: 'inbound', source_id: 'inbound-1' }, result: 'completed', rate_kopecks: 600, amount_kopecks: 1200, invoice_history: { state: 'known', count: 0 } }] }) }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-seller-finance').click()
  await expect(page.getByRole('columnheader', { name: 'Начислено' })).toBeVisible()
  await page.getByRole('button', { name: 'Показать операции' }).click()
  await expect(page.getByTestId('billing-seller-storage').locator('tbody tr')).toHaveCount(1)
  await expect(page.getByTestId('billing-seller-entries').getByRole('columnheader', { name: 'Счёт выставлялся' })).toBeVisible()
  await expect(page.getByText('По исполнителям')).toHaveCount(0)
  // Волна 4: выбор операции появился, но подпись чекбокса скрыта — колонка узкая.
  const pick = page.getByTestId('billing-seller-entries').getByRole('checkbox')
  await expect(pick).toHaveCount(1)
  await expect(pick).toHaveAttribute('aria-label', /Выбрать операцию/)
})
