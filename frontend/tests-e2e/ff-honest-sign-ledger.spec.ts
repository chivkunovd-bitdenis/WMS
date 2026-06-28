import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { selectHonestSignSeller, selectMarkingSeller } from './ff-honest-sign-helpers'

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

async function fillLedgerDateField(page: import('@playwright/test').Page, testId: string, value: string) {
  await page.getByTestId(testId).locator('input').fill(value)
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
  await selectHonestSignSeller(page, sellerId)
  await page.getByTestId('ff-honest-sign-open-ledger').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-page')).toBeVisible()
  await selectMarkingSeller(page, 'ff-honest-sign-ledger', sellerId)
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('Импорт')

  await Promise.all([
    waitForLedgerGet(page, 'event_type=printed'),
    page.getByTestId('ff-honest-sign-ledger-event-type').click(),
    page.getByRole('option', { name: 'Печать' }).click(),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).not.toContainText('Импорт')

  await Promise.all([
    waitForLedgerGet(page, 'event_type=imported'),
    page.getByTestId('ff-honest-sign-ledger-event-type').click(),
    page.getByRole('option', { name: 'Импорт' }).click(),
  ])
  await Promise.all([
    waitForLedgerGet(page, `document=${encodeURIComponent(docNumber)}`),
    page.getByRole('textbox', { name: 'Документ' }).fill(docNumber),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText(docNumber)

  const today = new Date().toISOString().slice(0, 10)
  await fillLedgerDateField(page, 'ff-honest-sign-ledger-date-from', today)
  const [todayLedgerRes] = await Promise.all([
    waitForLedgerGet(page, 'date_to='),
    fillLedgerDateField(page, 'ff-honest-sign-ledger-date-to', today),
  ])
  expect(todayLedgerRes.url()).toContain('date_from=')
  expect(todayLedgerRes.url()).toContain('date_to=')
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('Импорт')

  await fillLedgerDateField(page, 'ff-honest-sign-ledger-date-from', '2099-01-01')
  await Promise.all([
    waitForLedgerGet(page, 'date_to=2099-01-01'),
    fillLedgerDateField(page, 'ff-honest-sign-ledger-date-to', '2099-01-01'),
  ])
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('События не найдены')
})

// TC-NEW-011 — CROSS-03: лента расхода — Autocomplete селлера (как на экране пулов).
test('FF honest sign ledger: seller autocomplete on ledger page', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-ledger-sel-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Ledger Sel')
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

  const sellerA = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Ledger Seller A', email: `led-a-${Date.now()}@example.com` }),
  })
  const sellerAId = String(((await sellerA.json()) as { id: string }).id)

  const sellerB = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Ledger Seller B', email: `led-b-${Date.now()}@example.com` }),
  })
  const sellerBId = String(((await sellerB.json()) as { id: string }).id)

  const gtin = '00000000005555'
  const cis = `01${gtin}21${'M'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerAId,
      pools_json: JSON.stringify([{ title: 'Ledger A Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await page.getByTestId('ff-honest-sign-open-ledger').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-ledger-seller-picker')).toBeVisible()

  await selectMarkingSeller(page, 'ff-honest-sign-ledger', sellerAId)
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('Импорт')

  await selectMarkingSeller(page, 'ff-honest-sign-ledger', sellerBId)
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).not.toContainText('Импорт')
})

// TC-NEW-LEDGER-04 — LEDGER-04: экспорт CSV по текущим фильтрам.
test('FF honest sign ledger: export CSV with current filters', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-ledger-export-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Ledger Export')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const bearer = { Authorization: `Bearer ${token}` }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: { ...bearer, 'Content-Type': 'application/json' },
    data: JSON.stringify({ name: 'Export Seller', email: `exp-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000006666'
  const cis = `01${gtin}21${'E'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Export Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await page.getByTestId('ff-honest-sign-open-ledger').click()
  await selectMarkingSeller(page, 'ff-honest-sign-ledger', sellerId)
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('Импорт')

  const [exportRes] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/operations/marking-codes/ledger/export') &&
        res.request().method() === 'GET' &&
        res.status() === 200,
    ),
    page.getByTestId('ff-honest-sign-ledger-export').click(),
  ])
  const contentType = exportRes.headers()['content-type'] ?? ''
  expect(contentType).toMatch(/text\/csv|application\/octet-stream/)
  const exportApi = await page.request.get(exportRes.url(), { headers: bearer })
  expect(exportApi.ok()).toBeTruthy()
  const body = await exportApi.text()
  expect(body.replace(/^\ufeff/, '')).toContain('imported')
})
