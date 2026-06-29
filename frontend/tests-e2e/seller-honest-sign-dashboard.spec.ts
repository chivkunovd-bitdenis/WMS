import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-006 — T3.4: дашборд остатков селлера (product-first), кнопка «Догрузить» открывает импорт.
test('seller honest sign dashboard shows product card and upload opens import', async ({ page }) => {
  const adminEmail = `e2e-seller-dash-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-seller-dash-sl-${Date.now()}@example.com`
  const password = 'password123'
  const sku = `SKU-DASH-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller Dash FF')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  const created = await page.request.post('/api/sellers/with-account', {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()
  const sellerId = String(((await created.json()) as { seller_id: string }).seller_id)

  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Item',
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
  const sellerBearer = { Authorization: `Bearer ${sellerToken}` }

  const gtin = '4601234567890'
  const cis = `01${gtin}21${'D'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: sellerBearer,
    multipart: {
      pools_json: JSON.stringify([{ title: 'E2E Dashboard Pool', product_ids: [productId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()

  await page.getByTestId('nav-seller-documents').click()
  await Promise.all([
    waitForGetOk(page, '/api/operations/marking-codes/inventory'),
    page.getByTestId('nav-seller-honest-sign').click(),
  ])
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-seller-dashboard')).toBeVisible()
  const card = page.getByTestId(`seller-honest-sign-product-card-${productId}`)
  await expect(card).toBeVisible()
  await expect(card).toContainText(sku)
  await expect(page.getByTestId(`seller-honest-sign-product-row-${productId}`)).toHaveCount(0)

  await card.getByTestId(`seller-honest-sign-product-card-upload-${productId}`).click()
  await expect(page.getByTestId('seller-honest-sign-import-dialog')).toBeVisible()
})
