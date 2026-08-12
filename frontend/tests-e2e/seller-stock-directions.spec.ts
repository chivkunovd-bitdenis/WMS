import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
} from './inbound-boxes-helpers'

// TC-NEW-STOCK-DIR-001 — seller product row: create FBS pool and reserve directions, then see compact stock distribution.
test('seller creates stock directions and sees FBS, reserves, free FBO', async ({ page }) => {
  test.setTimeout(120_000)
  const suffix = String(Date.now())
  const adminEmail = `e2e-stock-dir-${suffix}@example.com`
  const sellerEmail = `e2e-stock-dir-seller-${suffix}@example.com`
  const password = 'password123'
  const sku = `SKU-DIR-${suffix}`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Stock Directions')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
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
    data: JSON.stringify({ name: 'Direction Brand' }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)
  await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  })
  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH', code: `wh-dir-${suffix}` }),
  })
  const warehouseId = String(((await whRes.json()) as { id: string }).id)
  const locRes = await page.request.post(`${e2eApi}/warehouses/${warehouseId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'DIR-LOC' }),
  })
  const locationId = String(((await locRes.json()) as { id: string }).id)
  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Direction Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await productRes.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: warehouseId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 10,
      storage_location_id: locationId,
    }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  const { boxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, {
    boxCount: 1,
  })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, boxes, sku, [10])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.getByTestId('logout').click()
  await loginAsSeller(page, sellerEmail, password, { firstTime: true })
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible()

  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 0 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('10')

  await row.getByTestId(`seller-stock-directions-toggle-${productId}`).click()
  const panel = page.getByTestId(`seller-stock-directions-panel-${productId}`)
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('FBS-пул не выделен')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('FBS WB')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('3')
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/api/products/${productId}/stock-directions`) &&
        r.status() === 201,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 3 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('7')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Набор сентябрь')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('2')
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/api/products/${productId}/stock-directions`) &&
        r.status() === 201,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'резервы 2 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('5')
  await expect(panel).toContainText('FBS-пул')
  await expect(panel).toContainText('Резерв/набор')
})
