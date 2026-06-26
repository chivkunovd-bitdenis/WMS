import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-004 — T0.4: привязка товара к пулу ЧЗ, чип в панели пула.
test('FF honest sign: link product to marking pool shows chip', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-pool-link-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-POOL-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pool Link')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Pool Seller', email: `pool-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Пул-товар',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  const poolRes = await page.request.post(`${e2eApi}/operations/marking-codes/_e2e/pools`, {
    headers: auth,
    data: JSON.stringify({
      seller_id: sellerId,
      gtin: '04600000000123',
      title: 'E2E тестовый пул',
    }),
  })
  expect(poolRes.ok()).toBeTruthy()
  const poolId = String(((await poolRes.json()) as { pool_id: string }).pool_id)

  await page.getByTestId('nav-ff-honest-sign').click()
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible()
  await page.goto(
    `/app/ff/honest-sign?pool_id=${encodeURIComponent(poolId)}&pool_title=${encodeURIComponent('E2E тестовый пул')}`,
  )
  await page.getByTestId(`ff-honest-sign-seller-${sellerId}`).click()
  await expect(page.getByTestId('ff-honest-sign-pool-panel')).toBeVisible()

  await page.getByTestId('ff-honest-sign-pool-link-products').click()
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

  await expect(page.getByTestId(`ff-honest-sign-pool-linked-chip-${productId}`)).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-product-chips')).toContainText(sku)
})
