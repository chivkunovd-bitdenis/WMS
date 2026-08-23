import { test, expect } from '@playwright/test'

const invoice = { id: 'invoice-1', number: 'СЧ-2026-00041', period: '2026-07', seller_name: 'Луна', issued_at: '2026-08-01T00:00:00Z', total_amount: 48392, status: 'issued', ff_profile: { legal_name: 'ООО «Фулфилмент Волна»', inn: '7701234567' }, seller_profile: { legal_name: 'ООО «Луна Трейд»', inn: '7812345678' }, lines: [{ id: 'line-1', service_code: 'inbound', unit: 'item', quantity: 1245, rate: 12, amount: 14940, documents: [{ date: '2026-07-20', number: 'ПР-000141', quantity: 84, amount: 1008 }] }, { id: 'line-storage', service_code: 'storage_liter_day', unit: 'liter_day', quantity: 181900, rate: 0.08, amount: 14552, documents: [{ date: '2026-07-31', number: 'technical-storage-uuid', quantity: 181900, amount: 14552 }] }] }

// S-31-TC-013 — Given invoice formation is blocked, When the invoices endpoint returns its run issue, Then the admin sees the cause and its corrective action.
test('billing invoices show server-side formation issues separate from invoices', async ({ page }) => {
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      invoices: [],
      issues: [{ id: 'issue-1', seller_id: 'seller-1', seller_name: 'Луна', period: '2026-07', reason: 'missing_profile', message: 'Заполните реквизиты' }],
    }),
  }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Луна')
  await expect(page.getByTestId('billing-invoice-issues')).toContainText('Нет реквизитов')
  await expect(page.getByRole('button', { name: 'Открыть селлера' })).toBeVisible()
})

// S-31-TC-006 — Given the seller's blocking causes are resolved, When the admin retries formation,
// Then the primary action has a short label and the newly issued invoice becomes visible.
test('billing invoice retry uses a short action label and keeps the visible formation result', async ({ page }) => {
  const seller = { id: 'seller-1', name: 'Луна' }
  let formed = false
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
    body: JSON.stringify({ invoices: formed ? [invoice] : [], issues: [] }),
  }))
  await page.route(`**/api/billing/invoices/${seller.id}/*/form`, async (route) => {
    formationRequests += 1
    formed = true
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'issued' }) })
  })

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-seller').click()
  await page.getByRole('option', { name: seller.name }).click()

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

  await page.getByRole('button', { name: 'Показать документы' }).click()
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('ПР-000141')
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('84')
  await page.getByRole('button', { name: 'Показать документы' }).nth(1).click()
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('Расчёт хранения за июль 2026 г.')
  await expect(page.getByTestId('billing-invoice-documents')).not.toContainText('technical-storage-uuid')
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
  await expect(printed).toContainText('48 392,00 ₽')
  await expect(printed).not.toContainText('legal_name')
  await expect(printed.getByRole('button')).toHaveCount(0)
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
