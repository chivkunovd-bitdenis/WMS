import { test, expect, type Page } from '@playwright/test'

const invoice = { id: 'invoice-1', number: 'СЧ-2026-00041', period: '2026-07', seller_name: 'Луна', issued_at: '2026-08-01T00:00:00Z', total_amount: '2949200.00', status: 'issued', ff_profile: { legal_name: 'ООО «Фулфилмент Волна»', inn: '7701234567' }, seller_profile: { legal_name: 'ООО «Луна Трейд»', inn: '7812345678' }, lines: [{ id: 'line-1', service_code: 'inbound', unit: 'item', quantity: '1245.000', rate: '1200', amount: '1494000', documents: [{ date: '2026-07-20', number: 'ПР-000141', quantity: '1245.000', amount: '1494000' }] }, { id: 'line-storage', service_code: 'storage_liter_day', unit: 'liter_day', quantity: '181900.000', rate: '8', amount: '1455200', documents: [{ date: '2026-07-31', number: 'technical-storage-uuid', quantity: '181900.000', amount: '1455200' }] }] }

async function authenticateBillingAdmin(page: Page) {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-billing-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'billing-admin@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/sellers', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([{ id: 'seller-1', name: 'Луна' }]),
  }))
  for (const endpoint of ['warehouses', 'products', 'products/ff-catalog']) {
    await page.route(`**/api/${endpoint}`, async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    }))
  }
}

test.beforeEach(async ({ page }) => authenticateBillingAdmin(page))

// S-31-TC-004 — Given ledger values are returned in kopecks, When the administrator opens charges,
// Then the rate and amount are shown in rubles once, without a 100-fold overstatement.
test('billing charges display kopecks exactly once', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/ledger?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ entries: [{
      id: 'ledger-kopecks',
      entry_type: 'charge',
      occurred_at: '2026-08-20T10:00:00Z',
      seller_name: 'Луна',
      service_code: 'inbound',
      source_type: 'inbound_intake',
      source_id: 'inbound-1',
      document_number: 'ПР-000141',
      quantity: 1,
      unit: 'item',
      rate: 1200,
      amount: 63000,
      performer_name: null,
      problem: null,
    }] }),
  }))

  await page.goto('/app/ff/billing')

  const cells = page.getByTestId('billing-ledger-table').locator('tbody tr').first().getByRole('cell')
  await expect(cells.nth(6)).toHaveText('12,00 ₽')
  await expect(cells.nth(7)).toHaveText('630,00 ₽')
  await expect(cells.nth(7)).not.toHaveText('63 000,00 ₽')
})

// S-31-TC-017 — Given the seller billing profile blocks formation, Then the corrective action targets that seller.
test('billing invoice seller-profile issue targets the affected seller', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      invoices: [],
      issues: [{ id: 'seller-profile-issue', seller_id: 'seller-1', seller_name: 'Луна', period: '2026-07', reason: 'missing_seller_profile', message: 'Заполните реквизиты селлера' }],
    }),
  }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Луна')
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Нет реквизитов')
  await expect(page.getByRole('button', { name: 'Открыть настройки' })).toHaveCount(0)
  await expect(page.getByTestId('billing-invoice-issue-action-seller-profile-issue'))
    .toHaveAttribute('href', '/app/ff/sellers?seller_id=seller-1')
})

// S-31-TC-018 — Given the FF billing profile blocks formation, Then the corrective action targets FF billing settings.
test('billing invoice FF-profile issue targets FF billing settings', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      invoices: [],
      issues: [{ id: 'ff-profile-issue', seller_id: 'seller-1', seller_name: 'Луна', period: '2026-07', reason: 'missing_ff_profile', message: 'Заполните реквизиты ФФ' }],
    }),
  }))

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Нет реквизитов')
  await expect(page.getByTestId('billing-invoice-issue-action-ff-profile-issue'))
    .toHaveAttribute('href', '/app/ff/settings?tab=tariffs')
})

// S-31-TC-012 — Given an invoice is blocked by a missing tariff, Then the corrective action targets tariff settings.
test('billing invoice tariff issue targets tariff settings', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      invoices: [],
      issues: [{ id: 'unpriced-issue', seller_id: 'seller-1', seller_name: 'Луна', period: '2026-07', reason: 'unpriced', message: 'Нет тарифа' }],
    }),
  }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Луна')
  await expect(page.getByTestId('billing-invoice-issue-action-unpriced-issue'))
    .toHaveAttribute('href', '/app/ff/settings?tab=tariffs')
})

// S-31-TC-012 — Given a charge has no tariff, Then the corrective action targets tariff settings.
test('billing charge tariff issue targets tariff settings', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/ledger?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ entries: [{
      id: 'unpriced-charge',
      entry_type: 'charge',
      occurred_at: '2026-08-20T10:00:00Z',
      seller_name: 'Луна',
      service_code: 'inbound',
      source_type: 'inbound',
      source_id: 'inbound-1',
      document_number: 'ПР-000141',
      quantity: 1,
      unit: 'item',
      rate: null,
      amount: null,
      performer_name: null,
      problem: 'unpriced',
    }] }),
  }))

  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('billing-open-tariffs'))
    .toHaveAttribute('href', '/app/ff/settings?tab=tariffs')
})

// S-31-TC-006 — Given the seller's blocking causes are resolved, When the admin retries formation,
// Then the primary action has a short label and the newly issued invoice becomes visible.
test('billing invoice retry is offered only after the server confirms a blocking cause is resolved', async ({ page }) => {
  const seller = { id: 'seller-1', name: 'Луна' }
  let formed = false
  let causeResolved = false
  let formationRequests = 0

  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-billing-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'billing-admin@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/sellers', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([seller]),
  }))
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      invoices: formed ? [invoice] : [],
      issues: causeResolved ? [] : [{ id: 'issue-1', seller_id: seller.id, seller_name: seller.name, period: '2026-07', reason: 'unpriced' }],
    }),
  }))
  await page.route(`**/api/billing/invoices/${seller.id}/*/form`, async (route) => {
    formationRequests += 1
    formed = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'issued' }) })
  })

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.locator('[aria-label="Селлер"] [role="combobox"]').click()
  await page.getByRole('option', { name: seller.name }).click()

  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Нет тарифа')
  await expect(page.getByRole('button', { name: 'Повторить формирование', exact: true })).toBeDisabled()
  causeResolved = true
  await page.locator('[aria-label="Статус"] [role="combobox"]').click()
  await page.getByRole('option', { name: 'Выставлен' }).click()
  await page.locator('[aria-label="Статус"] [role="combobox"]').click()
  await page.getByRole('option', { name: 'Все статусы' }).click()

  await expect(page.getByText('Причины устранены — повторите формирование', { exact: true })).toBeVisible()
  const retry = page.getByRole('button', { name: 'Повторить формирование', exact: true })
  await expect(retry).toBeVisible()
  await expect(page.getByRole('button', { name: 'Причины устранены — повторите формирование', exact: true })).toHaveCount(0)

  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes(`/api/billing/invoices/${seller.id}/`) && response.url().endsWith('/form') && response.ok()),
    retry.click(),
  ])

  await expect(page.getByTestId('billing-invoices-table')).toContainText(invoice.number)
  await expect(page.getByTestId('billing-invoices-table')).toContainText('Выставлен')
  expect(formationRequests).toBe(1)
})

// S-31-TC-013 — Given the selected seller has no charges in the closed month, When the invoices API returns no invoice and no issue, Then the admin sees the normal empty state without a corrective action.
test('billing invoices show a normal empty month without retrying formation', async ({ page }) => {
  const seller = { id: 'seller-empty', name: 'Пустой месяц' }
  let formationRequests = 0

  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-billing-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'billing-admin@example.test', organization_name: 'ФФ Волна', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/sellers', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([seller]),
  }))
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ invoices: [], issues: [] }),
  }))
  await page.route(`**/api/billing/invoices/${seller.id}/*/form`, async (route) => {
    formationRequests += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'empty' }) })
  })

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.locator('[aria-label="Селлер"] [role="combobox"]').click()
  await page.getByRole('option', { name: seller.name }).click()

  await expect(page.getByTestId('billing-invoices-table')).toContainText('За этот месяц счета не выставлены')
  await expect(page.getByTestId('billing-invoices-table')).toContainText('Нет начислений для формирования')
  await expect(page.getByTestId('billing-invoice-issues')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Повторить формирование', exact: true })).toHaveCount(0)
  expect(formationRequests).toBe(0)
})

// S-31-TC-007 — Given an issued invoice, When the admin opens it, Then the six fixed columns stay aligned and document details and print remain available.
test('billing invoice opens, reveals documents and starts print', async ({ page }) => {
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ invoices: [invoice] }) }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-invoice-open-invoice-1').click()
  await expect(page.getByRole('dialog', { name: /Счёт СЧ-2026-00041/ })).toBeVisible()

  const linesTable = page.getByTestId('billing-invoice-lines')
  const fixedHeaders = [
    ['Услуга', '180'],
    ['Расчёт', '170'],
    ['Количество', '120'],
    ['Ставка', '130'],
    ['Сумма', '140'],
    ['Детализация', '70'],
  ] as const
  for (const [name, width] of fixedHeaders) {
    await expect(linesTable.getByRole('columnheader', { name, exact: true })).toHaveAttribute('width', width)
  }
  for (const name of ['Количество', 'Ставка', 'Сумма']) {
    await expect(linesTable.getByRole('columnheader', { name, exact: true })).toHaveCSS('text-align', 'right')
  }
  await expect(linesTable.getByRole('columnheader', { name: 'Детализация', exact: true })).toHaveCSS('text-align', 'center')

  const firstLineCells = linesTable.locator('tbody tr').first().getByRole('cell')
  await expect(firstLineCells).toHaveCount(6)
  await expect(firstLineCells.nth(0)).toHaveText('Приёмка')
  await expect(firstLineCells.nth(1)).toHaveText('За штуку')
  await expect(firstLineCells.nth(2)).toHaveText('1 245')
  await expect(firstLineCells.nth(3)).toHaveText('12,00 ₽')
  await expect(firstLineCells.nth(4)).toHaveText('14 940,00 ₽')
  for (const index of [2, 3, 4]) {
    await expect(firstLineCells.nth(index)).toHaveCSS('text-align', 'right')
  }
  await expect(firstLineCells.nth(5)).toHaveCSS('text-align', 'center')

  await page.locator('[aria-label="Показать документы"] button').first().click()
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('ПР-000141')
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('1 245')
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('14 940,00 ₽')
  await page.locator('[aria-label="Показать документы"] button').nth(1).click()
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('Расчёт хранения за июль 2026 г.')
  await expect(page.getByTestId('billing-invoice-documents')).not.toContainText('technical-storage-uuid')
  await expect(page.getByTestId('billing-invoice-documents')).not.toContainText('· ·')
  expect(((await page.getByTestId('billing-invoice-documents').textContent())?.match(/·/g) ?? []).length).toBe(3)
  const pageGeometry = await page.evaluate(() => ({
    contentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }))
  expect(pageGeometry.contentWidth).toBeLessThanOrEqual(pageGeometry.viewportWidth)
  await page.screenshot({ path: '../docs/evidence/20260823-billing-stage-finish/billing-invoice.png', fullPage: true })
  await expect(page.getByRole('dialog', { name: /Счёт СЧ-2026-00041/ })).not.toContainText('storage_liter_day')
  const printWindow = page.waitForEvent('popup')
  await Promise.all([
    printWindow,
    page.getByTestId('billing-invoice-print').click(),
  ])
  const printed = (await printWindow).locator('body')
  await expect(printed).toContainText('СЧ-2026-00041')
  await expect(printed).toContainText('ООО «Фулфилмент Волна»')
  await expect(printed).toContainText('ООО «Луна Трейд»')
  await expect(printed).toContainText('29 492,00 ₽')
  await expect(printed).not.toContainText('legal_name')
  await expect(printed.getByRole('button')).toHaveCount(0)
})

// S-31-TC-007 — Given an invoice line with an unknown service and unit, When the admin opens and prints it,
// Then the dialog and print view show safe placeholders and a clear notice without exposing technical values.
test('billing invoice hides unknown service and unit codes', async ({ page }) => {
  const unknownService = 'manual_dark_store_fee'
  const unknownUnit = 'pallet_moon'
  const invoiceWithUnknownCodes = {
    ...invoice,
    id: 'invoice-unknown-code',
    number: 'СЧ-2026-00999',
    lines: [{
      id: 'line-unknown-code',
      service_code: unknownService,
      unit: unknownUnit,
      quantity: 2,
      rate: 100,
      amount: 200,
      documents: [],
    }],
  }
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ invoices: [invoiceWithUnknownCodes] }),
  }))

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-invoice-open-invoice-unknown-code').click()

  await expect(page.getByTestId('billing-invoice-data-error')).toContainText('нераспознанной услугой или расчётом')
  const lineCells = page.getByTestId('billing-invoice-lines').locator('tbody tr').first().getByRole('cell')
  await expect(lineCells.nth(0)).toHaveText('—')
  await expect(lineCells.nth(1)).toHaveText('—')
  await expect(page.getByText(unknownService, { exact: true })).toHaveCount(0)
  await expect(page.getByText(unknownUnit, { exact: true })).toHaveCount(0)

  const printWindow = page.waitForEvent('popup')
  await Promise.all([
    printWindow,
    page.getByTestId('billing-invoice-print').click(),
  ])
  const printed = (await printWindow).locator('body')
  await expect(printed.locator('tbody tr').first().locator('td').nth(0)).toHaveText('—')
  await expect(printed.locator('tbody tr').first().locator('td').nth(1)).toHaveText('—')
  await expect(printed).not.toContainText(unknownService)
  await expect(printed).not.toContainText(unknownUnit)
})

// S-31-TC-008 — Given an issued invoice, When cancellation is confirmed twice, Then history has one cancelled invoice and no second cancellation request.
test('billing invoice cancellation is confirmed and idempotent in UI', async ({ page }) => {
  let cancellations = 0
  let releaseCancellation: () => void = () => undefined
  const cancellationGate = new Promise<void>((resolve) => { releaseCancellation = () => resolve() })
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ invoices: [invoice] }) }))
  await page.route('**/api/billing/invoices/invoice-1/cancel', async (route) => { cancellations += 1; await cancellationGate; await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'invoice-1', status: 'cancelled' }) }) })
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-invoice-open-invoice-1').click()
  await page.getByTestId('billing-invoice-cancel').click()
  await expect(page.getByText('Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.')).toBeVisible()
  const confirmCancellation = page.getByTestId('billing-invoice-cancel-confirm')
  await confirmCancellation.click()
  await expect(confirmCancellation).toBeDisabled()
  await confirmCancellation.dispatchEvent('click')
  releaseCancellation()
  await expect(page.getByText('Отменён')).toBeVisible()
  await expect(page.getByTestId('billing-invoice-cancel')).toHaveCount(0)
  expect(cancellations).toBe(1)
})
