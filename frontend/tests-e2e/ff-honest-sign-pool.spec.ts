import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-009 — T0.9: вкладки карточки пула и экспорт CSV кодов.
// TC-NEW-011 — T-E3: таб «Лента» — превью + ссылка на полную ленту пула (без дубля).
test('FF honest sign pool card: tabs and CSV export', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-pool-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pool Card')
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
    data: JSON.stringify({ name: 'Pool Card Seller', email: `pc-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000005555'
  const cis = `01${gtin}21${'P'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Card Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()
  const poolId = String(((await imp.json()) as { pools: { pool_id: string }[] }).pools[0].pool_id)

  await page.getByTestId('nav-ff-honest-sign').click()
  await page.getByTestId(`ff-honest-sign-seller-${sellerId}`).click()
  await page.getByTestId(`ff-honest-sign-pool-row-${poolId}`).click()
  await expect(page.getByTestId('ff-honest-sign-pool-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-overview')).toBeVisible()

  await page.getByTestId('ff-honest-sign-pool-tab-products').click()
  await expect(page.getByTestId('ff-honest-sign-pool-products')).toBeVisible()

  await page.getByTestId('ff-honest-sign-pool-tab-codes').click()
  await expect(page.getByTestId('ff-honest-sign-pool-codes')).toBeVisible()
  await expect(page.locator('[data-testid^="ff-honest-sign-pool-code-row-"]')).toHaveCount(1)

  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('ff-honest-sign-pool-codes-export').click()
  const download = await downloadPromise
  const path = await download.path()
  expect(path).toBeTruthy()

  await page.getByTestId('ff-honest-sign-pool-tab-ledger').click()
  await expect(page.getByTestId('ff-honest-sign-pool-ledger-preview')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-ledger-open-full')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-ledger-event-type')).toHaveCount(0)
  await expect(page.getByTestId('ff-honest-sign-pool-ledger-preview')).toContainText('Импорт')
  await page.getByTestId('ff-honest-sign-pool-ledger-open-full').click()
  await expect(page.getByTestId('ff-honest-sign-ledger-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-ledger-table')).toContainText('Импорт')
})

// TC-NEW-012 — FINAL-02: legacy /import route redirects to pool list (no stub duplicate).
test('FF honest sign: import route redirects to pool list', async ({ page }) => {
  test.setTimeout(60_000)
  const email = `e2e-imp-redir-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Import Redirect')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await page.goto('/app/ff/honest-sign/import')
  await expect(page).toHaveURL(/\/app\/ff\/honest-sign\/?$/)
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-import-page')).toHaveCount(0)
})
