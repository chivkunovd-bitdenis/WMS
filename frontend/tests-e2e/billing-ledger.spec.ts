import { test, expect, type Page } from '@playwright/test'

async function authenticateBillingAdmin(page: Page) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-billing-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'billing-admin@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }),
  }))
  for (const endpoint of ['warehouses', 'products', 'products/ff-catalog', 'sellers']) {
    await page.route(`**/api/${endpoint}`, async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    }))
  }
}

test.beforeEach(async ({ page }) => authenticateBillingAdmin(page))

// S-31-TC-004 — Given ledger rows, When the admin filters by document, Then the visible row keeps the month context.
test('billing ledger preserves filters and month context', async ({ page }) => {
  let lastLedgerUrl = ''
  await page.route('**/api/billing/ledger**', async (route) => {
    lastLedgerUrl = route.request().url()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-1', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', source_type: 'inbound_intake', source_id: 'inbound-1', document_number: 'ПР-000184', quantity: '38.0000', unit: 'item', rate: '12', amount: '456', performer_name: 'Анна К.', problem: null }] }) })
  })
  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('ff-billing-screen')).toBeVisible()
  await expect(page.getByText('ПР-000184')).toBeVisible()
  const pageGeometry = await page.evaluate(() => ({
    contentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    offenders: [...document.querySelectorAll<HTMLElement>('body *')]
      .map((element) => ({
        tag: element.tagName,
        testId: element.dataset.testid ?? '',
        className: String(element.className),
        right: Math.round(element.getBoundingClientRect().right),
        width: Math.round(element.getBoundingClientRect().width),
      }))
      .filter((element) => element.right > document.documentElement.clientWidth + 1)
      .slice(0, 12),
  }))
  expect(pageGeometry.contentWidth, JSON.stringify(pageGeometry.offenders)).toBeLessThanOrEqual(pageGeometry.viewportWidth)
  const ledgerTable = page.getByTestId('billing-ledger-table')
  const tableGeometry = await ledgerTable.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }))
  expect(tableGeometry.scroll).toBeLessThanOrEqual(tableGeometry.client)
  await expect(ledgerTable.getByRole('columnheader', { name: 'Документ', exact: true })).toBeVisible()
  await expect(ledgerTable.getByRole('columnheader', { name: 'Исполнитель / проблема', exact: true })).toBeVisible()
  await expect(ledgerTable.getByRole('columnheader')).toHaveCount(6)
  await page.screenshot({ path: '../docs/evidence/20260823-billing-stage-finish/billing-charges.png', fullPage: true })
  await page.screenshot({ path: '../docs/evidence/20260823-billing-stage-finish/billing-charges-right.png', fullPage: true })
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
  await page.locator('[aria-label="Режим"] [role="combobox"]').click()
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

// S-31-TC-016 — Given a completed operation and its reversal by another user, When the admin opens performer mode,
// Then the reversal is not counted as the cancelling user's work; its marked operation row still opens the original document.
test('billing ledger excludes reversals from performer totals and keeps their source document link', async ({ page }) => {
  await page.route('**/api/billing/ledger**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ entries: [
      {
        id: 'charge-entry',
        entry_type: 'charge',
        occurred_at: '2026-08-18T00:00:00Z',
        seller_name: 'Луна',
        service_code: 'inbound',
        source_type: 'inbound_intake',
        source_id: 'inbound-original',
        document_number: 'ПР-000184',
        quantity: 20,
        unit: 'item',
        rate: 12,
        amount: 240,
        performer_name: 'Анна К.',
        problem: null,
      },
      {
        id: 'reversal-entry',
        entry_type: 'reversal',
        occurred_at: '2026-08-19T00:00:00Z',
        seller_name: 'Луна',
        service_code: 'inbound',
        source_type: 'inbound_intake',
        source_id: 'inbound-original',
        document_number: 'ПР-000184',
        quantity: -20,
        unit: 'item',
        rate: 12,
        amount: -240,
        performer_name: 'Борис Р.',
        problem: null,
      },
    ] }),
  }))

  await page.goto('/app/ff/billing')
  await page.locator('[aria-label="Режим"] [role="combobox"]').click()
  await page.getByRole('option', { name: 'По исполнителям' }).click()

  const table = page.getByTestId('billing-ledger-table')
  await expect(table.getByRole('cell', { name: 'Анна К.', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: '20', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: 'Борис Р.', exact: true })).toHaveCount(0)
  await expect(table.getByRole('cell', { name: '-20', exact: true })).toHaveCount(0)

  await page.locator('[aria-label="Режим"] [role="combobox"]').click()
  await page.getByRole('option', { name: 'По операциям' }).click()
  const reversalDocument = page.getByTestId('billing-document-reversal-entry')
  await expect(reversalDocument).toHaveText('Сторно ПР-000184')
  await reversalDocument.click()
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible()
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
  await page.route('**/api/billing/ledger**', async (route) => {
    const period = new URL(route.request().url()).searchParams.get('period')
    if (period !== '2026-07') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: [{ id: 'entry-stale', occurred_at: '2026-08-18T00:00:00Z', seller_name: 'Луна', service_code: 'inbound', document_number: 'ПР-000184', quantity: 1, unit: 'document', rate: 12, amount: 12, performer_name: 'Анна К.', problem: null }] }) })
      return
    }
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
  })
  await page.goto('/app/ff/billing')
  await expect(page.getByText('ПР-000184')).toBeVisible()
  await page.getByTestId('billing-period').fill('2026-07')
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
  await page.locator('[aria-label="Услуга"] [role="combobox"]').click()
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
  await expect(operationCells.nth(3)).toContainText('—')
  await expect(page.getByText(unknownService, { exact: true })).toHaveCount(0)
  await expect(page.getByText(unknownUnit, { exact: true })).toHaveCount(0)

  await page.locator('[aria-label="Режим"] [role="combobox"]').click()
  await page.getByRole('option', { name: 'По исполнителям' }).click()
  const performerCells = table.locator('tbody tr').first().getByRole('cell')
  await expect(performerCells.nth(1)).toHaveText('—')
  await expect(performerCells.nth(2)).toHaveText('—')
  await expect(page.getByText(unknownService, { exact: true })).toHaveCount(0)
  await expect(page.getByText(unknownUnit, { exact: true })).toHaveCount(0)
})
