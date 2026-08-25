import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
} from './inbound-boxes-helpers'

// Stock directions are warehouse-managed; the seller can only inspect the resulting reserves.
test('seller sees warehouse-managed stock directions in the reserves drawer', async ({ page }) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1280, height: 720 })
  const suffix = String(Date.now())
  const adminEmail = `e2e-stock-dir-${suffix}@example.com`
  const sellerEmail = `e2e-stock-dir-seller-${suffix}@example.com`
  const password = 'password123'
  const sku = `SKU-DIR-${suffix}`
  const e2eApi =
    process.env.E2E_API_ORIGIN ??
    `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

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

  const directionRes = await page.request.post(
    `${e2eApi}/products/${productId}/stock-directions`,
    {
      headers: auth,
      data: JSON.stringify({
        name: 'Набор сентябрь',
        comment: 'Резерв создан складом',
        quantity: 4,
        is_fbs: false,
      }),
    },
  )
  expect(directionRes.status()).toBe(201)
  const directionId = String(((await directionRes.json()) as { id: string }).id)

  await page.getByTestId('logout').click()
  await loginAsSeller(page, sellerEmail, password, { firstTime: true })
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible()

  const tableHead = page.getByTestId('seller-products-table').locator('thead')
  await expect(tableHead).toContainText('Артикул продавца')
  await expect(tableHead).toContainText('Остаток')
  await expect(tableHead).toContainText('Резервы')
  await expect(tableHead).not.toContainText('Публикация WB')
  await expect(tableHead).not.toContainText('FBS-пул')

  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(row.getByTestId(`seller-catalog-stock-in-storage-${productId}`)).toHaveText(
    'В ячейках 10',
  )
  await expect(row.getByTestId(`seller-catalog-stock-on-hand-${productId}`)).toHaveText(
    'На ФФ 10',
  )
  await expect(row.getByTestId(`seller-catalog-stock-free-fbo-${productId}`)).toHaveText(
    'Свободный FBO 6',
  )
  await expect(row.locator('[data-testid^="seller-stock-direction-"]')).toHaveCount(0)

  await row.getByTestId(`seller-catalog-reserves-${productId}`).click()
  const drawer = page.getByTestId(`seller-reserves-panel-${productId}`)
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText(/Резервы\s*4 шт/)
  await expect(drawer).toContainText(/Свободный FBO\s*6 шт/)
  await expect(drawer.getByTestId(`seller-reserve-direction-row-${directionId}`)).toContainText(
    'Набор сентябрь',
  )
  await expect(drawer.getByTestId(`seller-reserve-direction-row-${directionId}`)).toContainText(
    'Резерв/набор · 4 шт',
  )
  await expect(drawer).not.toContainText('Редактировать направление')
  await expect(drawer).not.toContainText('Удалить')
})
