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

// TC-NEW-F08-001/002/003/004 — FF manages ordinary stock directions and the
// per-product FBS publication limit from the current catalog UI.
test('ff manages stock directions and the product FBS limit from the catalog', async ({ page }) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1280, height: 720 })
  const suffix = String(Date.now())
  const adminEmail = `e2e-stock-dir-${suffix}@example.com`
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

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-table')).toBeVisible()
  const tableHead = page.getByTestId('ff-products-table').locator('thead')
  await expect(tableHead).toContainText('Артикул продавца')
  await expect(tableHead).toContainText('Остаток')
  await expect(tableHead).toContainText('Резервы')
  await expect(tableHead).not.toContainText(/WB nm|nmID|nm_id/)

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
  await expect(panel).toContainText('Направлений пока нет.')

  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Набор сентябрь')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('2')
  const [createRes] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/api/products/${productId}/stock-directions`) &&
        response.status() === 201,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  const directionId = String(((await createRes.json()) as { id: string }).id)
  await expect(panel.getByTestId(`ff-stock-direction-row-${directionId}`)).toContainText(
    'Резерв/набор · 2 шт',
  )
  await expect(row.getByTestId(`ff-catalog-stock-free-fbo-${productId}`)).toHaveText(
    'Свободный FBO 8',
  )

  await page.getByTestId(`ff-stock-direction-edit-${directionId}`).click()
  await expect(panel).toContainText('Редактировать направление')
  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Набор сентябрь — обновлён')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('4')
  await page
    .getByTestId(`ff-stock-direction-comment-${productId}`)
    .fill('Комментарий остаётся внутри панели и не раздувает строку каталога')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        response.url().includes(`/api/products/stock-directions/${directionId}`) &&
        response.status() === 200,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  await expect(panel.getByTestId(`ff-stock-direction-row-${directionId}`)).toContainText(
    'Резерв/набор · 4 шт',
  )
  await expect(row.getByTestId(`ff-catalog-stock-free-fbo-${productId}`)).toHaveText(
    'Свободный FBO 6',
  )

  await page.getByTestId(`ff-stock-direction-name-${productId}`).fill('Слишком много')
  await page.getByTestId(`ff-stock-direction-quantity-${productId}`).fill('7')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/api/products/${productId}/stock-directions`) &&
        response.status() === 422,
    ),
    page.getByTestId(`ff-stock-direction-submit-${productId}`).click(),
  ])
  await expect(page.getByTestId('ff-products-error')).toBeVisible()
  await expect(page.getByTestId('ff-products-error')).not.toContainText('directions_exceed_stock')

  let deleteRequests = 0
  page.on('request', (request) => {
    if (
      request.method() === 'DELETE' &&
      request.url().includes(`/api/products/stock-directions/${directionId}`)
    ) {
      deleteRequests += 1
    }
  })
  await page.getByTestId(`ff-stock-direction-delete-${directionId}`).click()
  const deleteDialog = page.getByTestId('ff-stock-direction-delete-dialog')
  await expect(deleteDialog).toBeVisible()
  await expect(deleteDialog).toContainText('Набор сентябрь — обновлён')
  await expect(deleteDialog).toContainText('4 шт')
  await deleteDialog.getByRole('button', { name: 'Отмена' }).click()
  expect(deleteRequests).toBe(0)
  await expect(panel.getByTestId(`ff-stock-direction-row-${directionId}`)).toBeVisible()

  await page.getByTestId(`ff-stock-direction-delete-${directionId}`).click()
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'DELETE' &&
        response.url().includes(`/api/products/stock-directions/${directionId}`) &&
        response.status() === 204,
    ),
    page.getByTestId('ff-stock-direction-confirm-delete').click(),
  ])
  expect(deleteRequests).toBe(1)
  await expect(panel.getByTestId(`ff-stock-direction-row-${directionId}`)).toHaveCount(0)
  await expect(row.getByTestId(`ff-catalog-stock-free-fbo-${productId}`)).toHaveText(
    'Свободный FBO 10',
  )
  await panel.getByRole('button', { name: 'Закрыть' }).click()
  await expect(panel).toBeHidden()

  // Product-level FBS publication is separate from WB warehouse binding and sync.
  // Keep this flow here so a catalog regression cannot silently stop publishing stock.
  await row.getByTestId(`ff-catalog-fbs-limit-${productId}`).click()
  const fbsLimitDialog = page.getByTestId('ff-catalog-fbs-limit-dialog')
  const fbsLimitInput = page.getByTestId('ff-catalog-fbs-limit-input')
  await expect(fbsLimitDialog).toBeVisible()
  await expect(fbsLimitInput).toHaveValue('')
  await fbsLimitInput.fill('3')
  const [setLimitRequest] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PATCH' &&
        request.url().includes(`/api/products/${productId}/fbs-stock-sync`),
    ),
    page.getByTestId('ff-catalog-fbs-limit-save').click(),
  ])
  expect(setLimitRequest.postDataJSON()).toEqual({ fbs_stock_limit: 3 })
  await expect(fbsLimitDialog).toBeHidden()
  await expect(page.getByText(`Остаток FBS для «${sku}» обновлён: 3 шт.`)).toBeVisible()

  await row.getByTestId(`ff-catalog-fbs-limit-${productId}`).click()
  await expect(fbsLimitInput).toHaveValue('3')
  await fbsLimitInput.fill('')
  const [clearLimitRequest] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PATCH' &&
        request.url().includes(`/api/products/${productId}/fbs-stock-sync`),
    ),
    page.getByTestId('ff-catalog-fbs-limit-save').click(),
  ])
  expect(clearLimitRequest.postDataJSON()).toEqual({ fbs_stock_limit: null })
  await expect(fbsLimitDialog).toBeHidden()
  await expect(page.getByText(`Остаток FBS для «${sku}» сброшен.`)).toBeVisible()

  await row.getByTestId(`ff-catalog-fbs-limit-${productId}`).click()
  await expect(fbsLimitInput).toHaveValue('')
  await fbsLimitDialog.getByRole('button', { name: 'Отмена' }).click()
})
