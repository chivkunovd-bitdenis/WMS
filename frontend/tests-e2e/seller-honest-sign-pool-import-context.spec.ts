import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-CROSS-004 — CROSS-04: «Догрузить» передаёт контекст пула в импорт.
test('seller pool card upload prefills import with pool context', async ({ page }) => {
  test.setTimeout(90_000)
  const adminEmail = `e2e-cross04-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-cross04-sl-${Date.now()}@example.com`
  const password = 'password123'
  const sku = `SKU-CROSS04-${Date.now()}`
  const gtin = '4601234567890'
  const poolTitle = 'E2E Cross04 Pool'
  const gtin14 = `0${gtin}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Cross04 FF')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const created = await page.request.post('/api/sellers/with-account', {
    headers: auth,
    data: JSON.stringify({
      name: 'Cross04 Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()
  const sellerId = String(((await created.json()) as { seller_id: string }).seller_id)

  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Cross04 Item',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(productRes.ok()).toBeTruthy()
  const productId = String(((await productRes.json()) as { id: string }).id)

  await loginAsSeller(page, sellerEmail, password, { firstTime: false })

  const sellerToken = await page.evaluate(() => localStorage.getItem('wms_token_seller'))
  expect(sellerToken).toBeTruthy()
  const sellerAuth = { Authorization: `Bearer ${sellerToken}` }

  const poolRes = await page.request.post('/api/operations/marking-codes/_e2e/pools', {
    headers: sellerAuth,
    data: { gtin, title: poolTitle },
  })
  expect(poolRes.ok()).toBeTruthy()
  const poolId = (await poolRes.json()).pool_id as string

  const linkRes = await page.request.put(
    `${e2eApi}/operations/marking-codes/pools/${poolId}/products`,
    {
      headers: { ...sellerAuth, 'Content-Type': 'application/json' },
      data: JSON.stringify({ product_ids: [productId] }),
    },
  )
  expect(linkRes.ok()).toBeTruthy()

  await page.getByTestId('nav-seller-honest-sign').click()
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-seller-dashboard')).toBeVisible()

  const card = page.getByTestId(`seller-honest-sign-pool-card-${poolId}`)
  await expect(card).toContainText(poolTitle)

  await card.getByTestId(`seller-honest-sign-pool-card-upload-${poolId}`).click()
  await expect(page.getByTestId('seller-honest-sign-import-dialog')).toBeVisible()
  const contextBanner = page.getByTestId('seller-honest-sign-import-pool-context')
  await expect(contextBanner).toBeVisible()
  await expect(contextBanner).toContainText(poolTitle)
  await expect(contextBanner).toContainText(gtin)

  const cis = `01${gtin14}21${'C'.repeat(20)}0001`
  const previewWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/import/preview') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await Promise.all([
    previewWait,
    page.getByTestId('seller-honest-sign-import-file-input').setInputFiles({
      name: 'cross04.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`cis\n${cis}`),
    }),
  ])

  await expect(page.getByTestId(`seller-honest-sign-import-group-${gtin14}`)).toBeVisible()
  await expect(
    page.getByTestId(`seller-honest-sign-import-title-${gtin14}`).getByRole('textbox'),
  ).toHaveValue(poolTitle)
  await expect(
    page.getByRole('checkbox', { name: `Привязать ${sku} к GTIN ${gtin14}` }),
  ).toBeChecked()
})
