import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
} from './inbound-boxes-helpers'

// TC-NEW-F08-001/002/003/004/005 — FF manages reserve directions in the FF catalog.
test('FF user creates, edits and deletes reserve directions in FF catalog', async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1280, height: 720 })
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

  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-table')).toBeVisible()
  const row = page.getByTestId('ff-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(row.getByTestId(`ff-catalog-stock-in-storage-${productId}`)).toHaveText(
    'В ячейках 10',
  )
  await expect(row.getByTestId(`ff-catalog-stock-on-hand-${productId}`)).toHaveText('На ФФ 10')
  await expect(row.getByTestId(`ff-catalog-stock-free-fbo-${productId}`)).toHaveText(
    'Свободный FBO 10',
  )

  await row.getByTestId(`ff-catalog-reserves-${productId}`).click()
  const panel = page.getByTestId(`ff-stock-directions-panel-${productId}`)
  await expect(panel).toBeVisible()

  const reserveSummary = panel.locator('.MuiTypography-caption').filter({ hasText: 'Резервы' })
  const freeFboSummary = panel
    .locator('.MuiTypography-caption')
    .filter({ hasText: 'Свободный FBO' })

  async function expectReserveTotals(reserves: number, freeFbo: number) {
    await expect(reserveSummary).toHaveCount(1)
    await expect(freeFboSummary).toHaveCount(1)
    await expect(reserveSummary.locator('..')).toContainText(`${reserves} шт`)
    await expect(freeFboSummary.locator('..')).toContainText(`${freeFbo} шт`)
    await expect(row.getByTestId(`ff-catalog-stock-free-fbo-${productId}`)).toHaveText(
      `Свободный FBO ${freeFbo}`,
    )
  }

  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Набор для заказа')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('3')
  const [firstCreateReq, firstCreateRes] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes(`/api/products/${productId}/stock-directions`),
    ),
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/api/products/${productId}/stock-directions`) &&
        response.status() === 201,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  expect((firstCreateReq.postDataJSON() as { is_fbs: boolean }).is_fbs).toBe(false)
  const firstDirectionId = String(((await firstCreateRes.json()) as { id: string }).id)
  await expect(panel.getByTestId(`ff-stock-direction-row-${firstDirectionId}`)).toContainText(
    'Резерв/набор · 3 шт',
  )
  await expectReserveTotals(3, 7)

  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Набор сентябрь')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('2')
  await page
    .getByTestId(`ff-stock-direction-comment-${productId}`)
    .fill('Комментарий к резерву')
  const [secondCreateReq, secondCreateRes] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes(`/api/products/${productId}/stock-directions`),
    ),
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/api/products/${productId}/stock-directions`) &&
        response.status() === 201,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  expect((secondCreateReq.postDataJSON() as { is_fbs: boolean }).is_fbs).toBe(false)
  const reserveDirectionId = String(((await secondCreateRes.json()) as { id: string }).id)
  await expect(panel.getByTestId(`ff-stock-direction-row-${reserveDirectionId}`)).toContainText(
    'Резерв/набор · 2 шт',
  )
  await expect(panel.locator('[data-testid^="ff-stock-direction-row-"]')).toHaveCount(2)
  await expectReserveTotals(5, 5)

  await page.getByTestId(`ff-stock-direction-edit-${reserveDirectionId}`).click()
  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Набор сентябрь long comment')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('4')
  await page
    .getByTestId(`ff-stock-direction-comment-${productId}`)
    .fill('Длинный комментарий не должен раздувать карточку направления')
  const [reservePatchReq, reservePatchRes] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PATCH' &&
        request.url().includes(`/api/products/stock-directions/${reserveDirectionId}`),
    ),
    page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        response.url().includes(`/api/products/stock-directions/${reserveDirectionId}`) &&
        response.status() === 200,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  expect((reservePatchReq.postDataJSON() as { is_fbs: boolean; quantity: number })).toMatchObject({
    is_fbs: false,
    quantity: 4,
  })
  expect(String(((await reservePatchRes.json()) as { id: string }).id)).toBe(reserveDirectionId)
  await expect(panel.getByTestId(`ff-stock-direction-row-${reserveDirectionId}`)).toContainText(
    'Резерв/набор · 4 шт',
  )
  await expectReserveTotals(7, 3)

  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Слишком много')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('4')
  const [overflowReq] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes(`/api/products/${productId}/stock-directions`),
    ),
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/api/products/${productId}/stock-directions`) &&
        response.status() === 422,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  expect((overflowReq.postDataJSON() as { is_fbs: boolean }).is_fbs).toBe(false)
  await expect(page.getByTestId('ff-products-error')).toContainText(
    'Нельзя распределить больше, чем есть на ФФ',
  )
  await expect(page.getByTestId('ff-products-error')).not.toContainText(
    'directions_exceed_stock',
  )
  await expectReserveTotals(7, 3)

  let deleteRequests = 0
  page.on('request', (request) => {
    if (
      request.method() === 'DELETE' &&
      request.url().includes(`/api/products/stock-directions/${firstDirectionId}`)
    ) {
      deleteRequests += 1
    }
  })
  await panel.getByTestId(`ff-stock-direction-delete-${firstDirectionId}`).click()
  const deleteDialog = page.getByTestId('ff-stock-direction-delete-dialog')
  await expect(deleteDialog).toBeVisible()
  await expect(deleteDialog).toContainText('Набор для заказа')
  await expect(deleteDialog).toContainText('3 шт')
  await deleteDialog.getByRole('button', { name: 'Отмена' }).click()
  expect(deleteRequests).toBe(0)
  await expect(panel.getByTestId(`ff-stock-direction-row-${firstDirectionId}`)).toBeVisible()

  await panel.getByTestId(`ff-stock-direction-delete-${firstDirectionId}`).click()
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'DELETE' &&
        response.url().includes(`/api/products/stock-directions/${firstDirectionId}`) &&
        response.status() === 204,
    ),
    page.getByTestId('ff-stock-direction-confirm-delete').click(),
  ])
  expect(deleteRequests).toBe(1)
  await expect(panel.getByTestId(`ff-stock-direction-row-${firstDirectionId}`)).toHaveCount(0)
  await expectReserveTotals(4, 6)

  const sellerAccountRes = await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  })
  expect(sellerAccountRes.ok()).toBeTruthy()
  await page.getByTestId('logout').click()
  await loginAsSeller(page, sellerEmail, password, { firstTime: true })
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible()
  const sellerRow = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(sellerRow).toBeVisible()
  await expect(
    sellerRow.getByTestId(`seller-catalog-stock-free-fbo-${productId}`),
  ).toHaveText('Свободный FBO 6')
  await sellerRow.getByTestId(`seller-catalog-reserves-${productId}`).click()
  const sellerPanel = page.getByTestId(`seller-reserves-panel-${productId}`)
  await expect(sellerPanel).toBeVisible()
  await expect(
    sellerPanel.getByTestId(`seller-reserve-direction-row-${reserveDirectionId}`),
  ).toContainText('Резерв/набор · 4 шт')
  const sellerReserveSummary = sellerPanel
    .locator('.MuiTypography-caption')
    .filter({ hasText: 'Резервы' })
  const sellerFreeFboSummary = sellerPanel
    .locator('.MuiTypography-caption')
    .filter({ hasText: 'Свободный FBO' })
  await expect(sellerReserveSummary).toHaveCount(1)
  await expect(sellerReserveSummary.locator('..')).toContainText('4 шт')
  await expect(sellerFreeFboSummary).toHaveCount(1)
  await expect(sellerFreeFboSummary.locator('..')).toContainText('6 шт')
  await expect(sellerPanel.getByRole('button', { name: 'Редактировать' })).toHaveCount(0)
  await expect(sellerPanel.getByRole('button', { name: 'Удалить' })).toHaveCount(0)
  await expect(sellerPanel.getByTestId('seller-reserves-close')).toBeVisible()
  await expect(sellerPanel.getByRole('button')).toHaveCount(1)
})
