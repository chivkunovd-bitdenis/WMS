import { test, expect } from '@playwright/test'

// S-31-TC-004 — Given ledger rows, When the admin filters by document, Then the visible row keeps the month context.
test('billing ledger preserves filters and month context', async ({ page }) => {
  let lastLedgerUrl = ''
  await page.route('**/api/billing/ledger**', async (route) => {
    lastLedgerUrl = route.request().url()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-1', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', source_type: 'inbound_intake', source_id: 'inbound-1', document_number: 'ПР-000184', quantity: 38, unit: 'item', rate: 12, amount: 456, performer_name: 'Анна К.', problem: null }] }) })
  })
  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('ff-billing-screen')).toBeVisible()
  await expect(page.getByText('ПР-000184')).toBeVisible()
  await expect.poll(() => new URL(lastLedgerUrl).searchParams.get('period')).toMatch(/^\d{4}-\d{2}$/)
  await expect.poll(() => new URL(lastLedgerUrl).searchParams.has('date')).toBe(false)
  await expect.poll(() => new URL(lastLedgerUrl).searchParams.has('seller_id')).toBe(false)
  await page.getByTestId('filter-search').fill('ПР-000184')
  await expect.poll(() => new URL(lastLedgerUrl).searchParams.get('document_number')).toBe('ПР-000184')
  await page.getByTestId('billing-tab-invoices').click()
  await expect(page.getByTestId('billing-invoices-table')).toBeVisible()
  await page.getByTestId('billing-tab-charges').click()
  await expect(page.getByText('ПР-000184')).toBeVisible()
  await page.getByTestId('billing-document-entry-1').click()
  await expect(page).toHaveURL('/app/ff/billing')
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible()
})

// S-31-TC-005 — Given completed work and a long performer name, When switching to performers,
// Then all five columns keep fixed boundaries, numeric columns stay right-aligned, and money columns are absent.
test('billing ledger performer mode keeps fixed columns and hides money', async ({ page }) => {
  const performerName = 'Александра Константиновна Очень-Длинная-Фамилия'
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-2', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', document_number: 'ПР-000184', quantity: 238, unit: 'item', rate: 12, amount: 2856, performer_name: performerName, problem: null }] }) }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-mode').click()
  await page.getByRole('option', { name: 'По исполнителям' }).click()

  const table = page.getByTestId('billing-ledger-table')
  const fixedHeaders = [
    ['Исполнитель', '220'],
    ['Услуга', '150'],
    ['Расчёт', '150'],
    ['Количество', '120'],
    ['Документов', '120'],
  ] as const
  for (const [name, width] of fixedHeaders) {
    await expect(table.getByRole('columnheader', { name, exact: true })).toHaveAttribute('width', width)
  }

  const performerCell = table.getByRole('cell', { name: performerName })
  await expect(performerCell).toBeVisible()
  const performerText = performerCell.locator('span').first()
  await expect(performerText).toHaveCSS('text-overflow', 'ellipsis')
  const performerTextWidth = await performerText.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }))
  expect(performerTextWidth.scroll).toBeGreaterThan(performerTextWidth.client)
  await expect(table.getByRole('cell', { name: 'Приёмка', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: 'За штуку', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: '238', exact: true })).toHaveCSS('text-align', 'right')
  await expect(table.getByRole('cell', { name: '1', exact: true })).toHaveCSS('text-align', 'right')
  await expect(page.getByRole('columnheader', { name: 'Сумма' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: 'Ставка' })).toHaveCount(0)
})

// S-31-TC-012 — Given a completed operation without a tariff, Then it remains visible and is marked as actionable.
test('billing ledger shows unpriced operation without blocking it', async ({ page }) => {
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-3', occurred_at: '2026-08-19T00:00:00Z', seller_name: 'Север', service_code: 'marketplace_outbound', document_number: 'ОТГ-000092', quantity: 1, unit: 'document', rate: null, amount: null, performer_name: 'Игорь М.', problem: 'unpriced' }] }) }))
  await page.goto('/app/ff/billing')
  await expect(page.getByText('Нет тарифа')).toBeVisible()
  await expect(page.getByText('ОТГ-000092')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Открыть тарифы' })).toBeVisible()
})

// S-31-TC-012 — Given a failed refresh after a visible row, Then stale ledger data is not presented as current.
test('billing ledger clears stale rows on load error', async ({ page }) => {
  let requestCount = 0
  await page.route('**/api/billing/ledger**', async (route) => {
    requestCount += 1
    if (requestCount === 1) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-stale', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', document_number: 'ПР-000184', quantity: 1, unit: 'document', rate: 12, amount: 12, performer_name: 'Анна К.', problem: null }] }) })
      return
    }
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
  })
  await page.goto('/app/ff/billing')
  await expect(page.getByText('ПР-000184')).toBeVisible()
  await page.getByTestId('billing-period').locator('input').fill('2026-07')
  await expect(page.getByTestId('billing-error')).toBeVisible()
  await expect(page.getByText('ПР-000184')).toHaveCount(0)
})

// S-31-TC-006 — Given a fixed storage charge, When the admin filters storage, Then the canonical service code is sent and no technical code is shown.
test('billing ledger uses the canonical storage service code', async ({ page }) => {
  let lastLedgerUrl = ''
  await page.route('**/api/billing/ledger**', async (route) => {
    lastLedgerUrl = route.request().url()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-storage', occurred_at: '2026-08-20T00:00:00Z', seller_name: 'Луна', service_code: 'storage_liter_day', document_number: 'Расчёт хранения за август', quantity: 84200, unit: 'liter_day', rate: 0.08, amount: 6736, performer_name: null, problem: null }] }) })
  })

  await page.goto('/app/ff/billing')
  await expect(page.getByText('Хранение', { exact: true })).toBeVisible()
  await expect(page.getByText('storage_liter_day')).toHaveCount(0)
  await page.getByTestId('billing-service').click()
  await page.getByRole('option', { name: 'Хранение' }).click()
  await expect.poll(() => new URL(lastLedgerUrl).searchParams.get('service_code')).toBe('storage_liter_day')
})

// S-31-TC-012 — Given an unknown service and unit from the API, When the admin views operations and performers,
// Then both modes show safe placeholders and a clear notice without exposing either technical value.
test('billing ledger hides unknown service and unit codes in both modes', async ({ page }) => {
  const unknownService = 'warehouse_magic_fee'
  const unknownUnit = 'crate_fortnight'
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ entries: [{
      id: 'entry-unknown-code',
      occurred_at: '2026-08-22T00:00:00Z',
      seller_name: 'Луна',
      service_code: unknownService,
      source_type: 'inbound_intake',
      source_id: 'inbound-unknown',
      document_number: 'ПР-000999',
      quantity: 7,
      unit: unknownUnit,
      rate: 10,
      amount: 70,
      performer_name: 'Анна К.',
      problem: null,
    }] }),
  }))

  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('billing-ledger-data-error')).toContainText('не удалось распознать услугу или расчёт')

  const table = page.getByTestId('billing-ledger-table')
  const operationCells = table.locator('tbody tr').first().getByRole('cell')
  await expect(operationCells.nth(2)).toHaveText('—')
  await expect(operationCells.nth(5)).toHaveText('—')
  await expect(page.getByText(unknownService, { exact: true })).toHaveCount(0)
  await expect(page.getByText(unknownUnit, { exact: true })).toHaveCount(0)

  await page.getByTestId('billing-mode').click()
  await page.getByRole('option', { name: 'По исполнителям' }).click()
  const performerCells = table.locator('tbody tr').first().getByRole('cell')
  await expect(performerCells.nth(1)).toHaveText('—')
  await expect(performerCells.nth(2)).toHaveText('—')
  await expect(page.getByText(unknownService, { exact: true })).toHaveCount(0)
  await expect(page.getByText(unknownUnit, { exact: true })).toHaveCount(0)
})
