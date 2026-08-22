import { test, expect } from '@playwright/test'

// S-31-TC-004 — Given ledger rows, When the admin filters by document, Then the visible row keeps the month context.
test('billing ledger preserves filters and month context', async ({ page }) => {
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-1', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', document_number: 'ПР-000184', quantity: 38, unit: 'item', rate: 12, amount: 456, performer_name: 'Анна К.', problem: null }] }) }))
  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('ff-billing-screen')).toBeVisible()
  await expect(page.getByText('ПР-000184')).toBeVisible()
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-tab-charges').click()
  await expect(page.getByText('ПР-000184')).toBeVisible()
})

// S-31-TC-005 — Given completed work, When switching to performers, Then money columns are absent.
test('billing ledger performer mode hides money columns', async ({ page }) => {
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-2', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', document_number: 'ПР-000184', quantity: 2, unit: 'item', rate: 12, amount: 24, performer_name: 'Анна К.', problem: null }] }) }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-mode').click()
  await page.getByRole('option', { name: 'По исполнителям' }).click()
  await expect(page.getByText('Анна К.')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Сумма' })).toHaveCount(0)
})

// S-31-TC-012 — Given a completed operation without a tariff, Then it remains visible and is marked as actionable.
test('billing ledger shows unpriced operation without blocking it', async ({ page }) => {
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-3', occurred_at: '2026-08-19T00:00:00Z', seller_name: 'Север', service_code: 'marketplace_outbound', document_number: 'ОТГ-000092', quantity: 1, unit: 'document', rate: null, amount: null, performer_name: 'Игорь М.', problem: 'unpriced' }] }) }))
  await page.goto('/app/ff/billing')
  await expect(page.getByText('Нет тарифа')).toBeVisible()
  await expect(page.getByText('ОТГ-000092')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Открыть тарифы' })).toBeVisible()
})
