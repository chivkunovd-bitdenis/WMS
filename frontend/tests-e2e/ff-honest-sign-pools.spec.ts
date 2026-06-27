import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-007 — T0.7: список пулов, меню «Привязать товары», переход в карточку пула.
test('FF honest sign: pool list row, link product via menu, open pool card', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-pools-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-PL-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pools')
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
    data: JSON.stringify({ name: 'E2E Pools Seller', email: `pl-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Pool Item',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  const gtin = '00000000008888'
  const cis = `01${gtin}21${'G'.repeat(20)}0001`
  const poolRes = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E List Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(poolRes.ok()).toBeTruthy()
  const poolId = String(((await poolRes.json()) as { pools: { pool_id: string }[] }).pools[0].pool_id)

  await page.getByTestId('nav-ff-honest-sign').click()
  await page.getByTestId(`ff-honest-sign-seller-${sellerId}`).click()
  const poolRow = page.getByTestId(`ff-honest-sign-pool-row-${poolId}`)
  await expect(poolRow).toBeVisible()
  await expect(poolRow).toContainText('E2E List Pool')
  await expect(poolRow).toContainText('1')

  await page.getByTestId(`ff-honest-sign-pool-menu-${poolId}`).click()
  await page.getByTestId('ff-honest-sign-menu-link-products').click()
  await expect(page.getByTestId('ff-honest-sign-pool-products-dialog')).toBeVisible()

  const saveWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'PUT' &&
      r.url().includes(`/operations/marking-codes/pools/${poolId}/products`) &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await page.getByRole('checkbox', { name: `Выбрать ${sku}` }).check()
  await Promise.all([saveWait, page.getByTestId('ff-honest-sign-pool-products-save').click()])
  await expect(page.getByTestId(`ff-honest-sign-pool-chip-${poolId}-${productId}`)).toBeVisible()

  await poolRow.click()
  await expect(page.getByTestId('ff-honest-sign-pool-page')).toBeVisible()
})
