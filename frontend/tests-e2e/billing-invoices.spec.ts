import { test, expect } from '@playwright/test'

const invoice = { id: 'invoice-1', number: 'СЧ-2026-00041', period: '2026-07', seller_name: 'Луна', issued_at: '2026-08-01T00:00:00Z', total_amount: 48392, status: 'issued', ff_profile: { legal_name: 'ООО «Фулфилмент Волна»', inn: '7701234567' }, seller_profile: { legal_name: 'ООО «Луна Трейд»', inn: '7812345678' }, lines: [{ id: 'line-1', service_code: 'inbound', unit: 'item', quantity: 1245, rate: 12, amount: 14940, documents: [{ date: '2026-07-20', number: 'ПР-000141', quantity: 84, amount: 1008 }] }] }

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

// S-31-TC-007 — Given an issued invoice, When the admin opens it, expands documents and prints, Then details are visible and print is started.
test('billing invoice opens, reveals documents and starts print', async ({ page }) => {
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ invoices: [invoice] }) }))
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-invoice-open-invoice-1').click()
  await expect(page.getByRole('dialog', { name: /Счёт СЧ-2026-00041/ })).toBeVisible()
  await page.getByRole('button', { name: 'Показать документы' }).click()
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('ПР-000141')
  await expect(page.getByTestId('billing-invoice-documents')).toContainText('84')
  const printWindow = page.waitForEvent('popup')
  await Promise.all([
    printWindow,
    page.getByTestId('billing-invoice-print').click(),
  ])
  const printed = (await printWindow).locator('body')
  await expect(printed).toContainText('СЧ-2026-00041')
  await expect(printed).toContainText('ООО «Фулфилмент Волна»')
  await expect(printed).toContainText('ООО «Луна Трейд»')
  await expect(printed.getByRole('button')).toHaveCount(0)
})

// S-31-TC-008 — Given an issued invoice, When cancellation is confirmed twice, Then history has one cancelled invoice and no second cancellation request.
test('billing invoice cancellation is confirmed and idempotent in UI', async ({ page }) => {
  let cancellations = 0
  await page.route('**/api/billing/invoices?**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ invoices: [invoice] }) }))
  await page.route('**/api/billing/invoices/invoice-1/cancel', async (route) => { cancellations += 1; await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'invoice-1', status: 'cancelled' }) }) })
  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-tab-invoices').click()
  await page.getByTestId('billing-invoice-open-invoice-1').click()
  await page.getByTestId('billing-invoice-cancel').click()
  await expect(page.getByText('Счёт останется в истории со статусом «Отменён». Это действие нельзя отменить.')).toBeVisible()
  await page.getByRole('button', { name: 'Отменить счёт' }).last().click()
  await expect(page.getByText('Отменён')).toBeVisible()
  await expect(page.getByTestId('billing-invoice-cancel')).toHaveCount(0)
  expect(cancellations).toBe(1)
})
