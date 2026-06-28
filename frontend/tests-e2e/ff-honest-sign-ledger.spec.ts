import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { selectHonestSignSeller, selectMarkingSeller } from './ff-honest-sign-helpers'

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
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('imported')

  await page.getByTestId('ff-honest-sign-ledger-event-type').click()
  await page.getByRole('option', { name: 'printed' }).click()
  await page.getByTestId('ff-honest-sign-ledger-apply').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).not.toContainText('imported')

  await page.getByTestId('ff-honest-sign-ledger-event-type').click()
  await page.getByRole('option', { name: 'imported' }).click()
  await page.getByRole('textbox', { name: 'Документ' }).fill(docNumber)
  await page.getByTestId('ff-honest-sign-ledger-apply').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText(docNumber)
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
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('imported')

  await selectMarkingSeller(page, 'ff-honest-sign-ledger', sellerBId)
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).not.toContainText('imported')
})
