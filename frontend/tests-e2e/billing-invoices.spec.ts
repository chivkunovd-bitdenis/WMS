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

// TC-NEW-007 — Given server seller totals in kopecks, When finance is on, Then money is formatted once.

// Вкладка «Счета» заменена на «Выставленные счета»: единый список старых
// месячных и новых счетов вместо помесячного среза. Проверки новой вкладки —
// billing-invoice-v2.spec.ts (TC-NEW-205..208), на настоящем сервере.
//
// Удалены как проверявшие механику, которой больше нет: повтор месячного
// формирования и пустой месяц (владелец автоматического выставления счетов не
// заказывал — ночная задача выпилена по TASK.FINAL), а также открытие, печать
// и отмена legacy-счёта — их заменили TC-NEW-205 и TC-NEW-206.
//
// Три проверки ниже отмечены fixme: причины блокировки (нет тарифа, нет
// реквизитов, хранение не закрыто) должны вернуться на вкладку «Селлеры» как
// причина недоступного чекбокса операции. Пока выбор операций не сделан,
// этой информации на экране нет — это известный пробел, а не решённый вопрос.

/**
 * Раскрыть строку селлера. Кнопки «Показать операции» и отдельной секции внизу
 * больше нет: подробности разворачиваются под самой строкой (ТЗ владельца
 * 27.08.2026, раздел 2).
 */
async function expandSeller(page: Page, name: string) {
  const row = page.getByTestId('billing-seller-summary').locator('tbody tr', { hasText: name }).first()
  await row.getByRole('button').first().click()
}

test('billing seller report displays kopecks exactly once', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/seller-report/summary?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ rows: [{
      seller_id: 'seller-1',
      seller_name: 'Луна',
      operation_count: 1,
      item_quantity: 1,
      not_billable_count: 0,
      unpriced_count: 0,
      net_total_kopecks: 63000,
      details_target: '/api/billing/seller-report/sellers/seller-1/details',
    }], totals: { seller_count: 1, operation_count: 1, item_quantity: 1, not_billable_count: 0, net_total_kopecks: 63000 } }),
  }))

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-seller-finance').click()
  const cells = page.getByTestId('billing-seller-summary').locator('tbody tr').first().getByRole('cell')
  await expect(cells.nth(6)).toHaveText('630,00 ₽')
  await expect(cells.nth(6)).not.toHaveText('63 000,00 ₽')
})

// S-31-TC-017 — Given the seller billing profile blocks formation, Then the corrective action targets that seller.

test.fixme('billing invoice seller-profile issue targets the affected seller', async ({ page }) => {
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

test.fixme('billing invoice FF-profile issue targets FF billing settings', async ({ page }) => {
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

test.fixme('billing invoice tariff issue targets tariff settings', async ({ page }) => {
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

// TC-NEW-008 — Given an unpriced seller operation, Then the report keeps it visible without invoice controls.

test('billing seller report keeps an unpriced operation visible', async ({ page }) => {
  await authenticateBillingAdmin(page)
  await page.route('**/api/billing/seller-report/summary?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ rows: [{
      seller_id: 'seller-1',
      seller_name: 'Луна',
      operation_count: 1,
      item_quantity: 1,
      not_billable_count: 0,
      unpriced_count: 1,
      net_total_kopecks: 0,
      details_target: '/api/billing/seller-report/sellers/seller-1/details',
    }], totals: { seller_count: 1, operation_count: 1, item_quantity: 1, not_billable_count: 0, unpriced_count: 1, net_total_kopecks: 0 } }),
  }))
  await page.route('**/api/billing/seller-report/sellers/seller-1/details?**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ seller_id: 'seller-1', seller_name: 'Луна', next_cursor: null, totals: { operation_count: 1, item_quantity: 1, not_billable_count: 0, unpriced_count: 1, net_total_kopecks: 0 }, storage_row: null, entries: [{ id: 'legacy_billing:unpriced', kind: 'legacy_billing', occurred_at: '2026-08-20T10:00:00+03:00', service_code: 'warehouse_magic_fee', item_quantity: 1, source_type: 'inbound', source_id: 'inbound-1', source_target: null, result: 'unpriced', amount_kopecks: null, rate_kopecks: null, invoice_history: { state: 'unknown' } }] }),
  }))

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-seller-finance').click()
  await expandSeller(page, 'Луна')
  await expect(page.getByTestId('billing-seller-entries')).toContainText('Нет ставки')
  await expect(page.getByText('warehouse_magic_fee', { exact: true })).toHaveCount(0)
  await page.getByText('Недоступен', { exact: true }).hover()
  await expect(page.getByRole('tooltip', { name: /Первоисточник недоступен/ })).toBeVisible()
  // Непроценённую операцию видно, но выбрать в счёт нельзя — причина названа.
  const unpriced = page.getByTestId('billing-seller-entries').getByRole('checkbox').last()
  await expect(unpriced).toBeDisabled()
  await expect(page.getByRole('button', { name: /Выставить счёт/ })).toHaveCount(1)
})

// S-31-TC-006 — Given the seller's blocking causes are resolved, When the admin retries formation,
// Then the primary action has a short label and the newly issued invoice becomes visible.
