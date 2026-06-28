import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { selectHonestSignSeller } from './ff-honest-sign-helpers'

// TC-NEW-002 — ЧЗ: список пулов после импорта через API.
test('FF honest sign: pool list shows imported available count', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-hs-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E HS')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const bearer = { Authorization: `Bearer ${token}` }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E HS Seller', email: `hs-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000005678'
  const cis = `01${gtin}21${'E'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'HS Pool', product_ids: [] }]),
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
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible()
  await selectHonestSignSeller(page, sellerId)
  await expect(page.getByTestId(`ff-honest-sign-pool-row-${poolId}`)).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-pool-row-${poolId}`)).toContainText('1')
})
