import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

function waitForLedgerGet(page: import('@playwright/test').Page, urlPart: string) {
  return page.waitForResponse(
    (res) =>
      res.url().includes('/operations/marking-codes/ledger') &&
      res.url().includes(urlPart) &&
      !res.url().includes('/export') &&
      res.request().method() === 'GET' &&
      res.status() === 200,
  )
}

// TC-NEW-010 — T0.10: лента расхода, фильтр по типу и документу.
test('FF honest sign ledger: imported events and document filter', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-ledger-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Ledger')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const bearer = { Authorization: `Bearer ${token}` }
  const auth = { ...bearer, 'Content-Type': 'application/json' }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Ledger Seller', email: `led-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000004444'
  const cis = `01${gtin}21${'L'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Ledger Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()
  const docNumber = String(((await imp.json()) as { document_number: string }).document_number)

  await page.getByTestId('nav-ff-honest-sign').click()
  await page.getByTestId(`ff-honest-sign-seller-${sellerId}`).click()
  await page.getByTestId('ff-honest-sign-open-ledger').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('imported')

  await Promise.all([
    waitForLedgerGet(page, 'event_type=printed'),
    page.getByTestId('ff-honest-sign-ledger-event-type').click(),
    page.getByRole('option', { name: 'printed' }).click(),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).not.toContainText('imported')

  await Promise.all([
    waitForLedgerGet(page, 'event_type=imported'),
    page.getByTestId('ff-honest-sign-ledger-event-type').click(),
    page.getByRole('option', { name: 'imported' }).click(),
  ])
  await Promise.all([
    waitForLedgerGet(page, `document=${encodeURIComponent(docNumber)}`),
    page.getByRole('textbox', { name: 'Документ' }).fill(docNumber),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText(docNumber)

  const today = new Date().toISOString().slice(0, 10)
  await page.getByTestId('ff-honest-sign-ledger-date-from').fill(today)
  const [todayLedgerRes] = await Promise.all([
    waitForLedgerGet(page, 'date_to='),
    page.getByTestId('ff-honest-sign-ledger-date-to').fill(today),
  ])
  expect(todayLedgerRes.url()).toContain('date_from=')
  expect(todayLedgerRes.url()).toContain('date_to=')
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('imported')

  await page.getByTestId('ff-honest-sign-ledger-date-from').fill('2099-01-01')
  await Promise.all([
    waitForLedgerGet(page, 'date_to=2099-01-01'),
    page.getByTestId('ff-honest-sign-ledger-date-to').fill('2099-01-01'),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('События не найдены')
})
