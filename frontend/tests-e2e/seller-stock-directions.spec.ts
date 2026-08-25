import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
} from './inbound-boxes-helpers'

// TC-NEW-F08-001/002/003/004/005 — seller manages compact stock directions through the Drawer only.
test('seller creates, edits and deletes stock directions with compact FBS publication controls', async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1280, height: 720 })
  const suffix = String(Date.now())
  const adminEmail = `e2e-stock-dir-${suffix}@example.com`
  const sellerEmail = `e2e-stock-dir-seller-${suffix}@example.com`
  const password = 'password123'
  const sku = `SKU-DIR-${suffix}`
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

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
  const tableHead = page.getByTestId('seller-products-table').locator('thead')
  await expect(tableHead).toContainText('Артикул WB')
  await expect(tableHead).not.toContainText('WB / ШК')
  await expect(tableHead).toContainText('FBS-пул')
  await expect(tableHead).toContainText('Публикация WB')
  await expect(tableHead).not.toContainText('Действия')
  await expect(tableHead).not.toContainText(/WB nm|nmID|nm_id/)
  await expect(page.getByTestId('seller-fbs-sync-panel')).toContainText('Публикация FBS в WB')
  await expect(page.getByTestId('seller-fbs-sync-panel')).not.toContainText('Включить всем')
  await expect(page.getByTestId('seller-fbs-sync-panel')).not.toContainText('Выключить всем')
  await expect(page.getByTestId('seller-fbs-sync-panel')).not.toContainText('Пауза публикации всем')
  await expect(page.getByTestId('seller-products-table')).not.toContainText('Лимит')
  await expect(page.getByTestId('seller-products-table')).not.toContainText(/pending_confirmation|warehouse_mapping_missing|wb_upstream_error|conflict/)
  await expect(page.getByTestId('seller-fbs-bulk-action')).toHaveCount(0)

  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 0 шт',
  )
  await expect(row.getByTestId('seller-stock-in-storage')).toHaveText('В ячейках 10')
  await expect(row.getByTestId('seller-stock-on-hand')).toHaveText('На ФФ 10')
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 10')
  await expect(row.getByTestId(`seller-stock-directions-toggle-${productId}`)).toHaveText('Пул')
  await expect(row.getByTestId(`seller-fbs-status-${productId}`)).toContainText(
    'Нет FBS',
  )
  await expect(row.getByTestId(`seller-fbs-toggle-${productId}`)).toBeDisabled()
  await expect(row.getByTestId(`seller-fbs-cell-${productId}`)).not.toContainText('Лимит')
  await expect(row.locator(`[data-testid="seller-fbs-limit-${productId}"]`)).toHaveCount(0)

  await row.getByTestId(`seller-product-select-${productId}`).click()
  await expect(page.getByTestId('seller-fbs-sync-panel')).toContainText('выбрано 1')
  await expect(page.getByTestId('seller-fbs-bulk-action')).toBeVisible()
  await page.getByTestId('seller-fbs-bulk-action').click()
  await expect(page.getByTestId('seller-fbs-bulk-enable')).toBeVisible()
  await page.getByTestId('seller-fbs-bulk-enable').click()
  const confirmDialog = page.getByTestId('seller-fbs-bulk-confirm-dialog')
  await expect(confirmDialog).toBeVisible()
  await expect(confirmDialog).toContainText('для 1 товаров')
  await expect(confirmDialog).toContainText('Будут изменены только выбранные товары')
  await expect(confirmDialog.getByTestId('seller-fbs-bulk-selected-list')).toContainText(sku)
  const [bulkPatchReq] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PATCH' &&
        request.url().includes('/api/products/fbs-stock-sync/bulk'),
    ),
    page.getByTestId('seller-fbs-bulk-confirm-submit').click(),
  ])
  const bulkPatchBody = bulkPatchReq.postDataJSON() as {
    product_ids: string[] | null
    fbs_stock_sync_enabled: boolean
  }
  expect(bulkPatchBody.product_ids).toEqual([productId])
  expect(bulkPatchBody.fbs_stock_sync_enabled).toBe(true)
  await expect(page.getByTestId('seller-fbs-bulk-result')).toContainText('Обновлено')
  await expect(page.getByTestId('seller-fbs-bulk-action')).toHaveCount(0)
  await expect(row.getByTestId(`seller-fbs-status-${productId}`)).toContainText('Нет FBS')

  await row.getByTestId(`seller-stock-directions-toggle-${productId}`).click()
  const panel = page.getByTestId(`seller-stock-directions-panel-${productId}`)
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('FBS-пул не выделен')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('FBS WB')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('3')
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
  const [fbsCreateRes] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/api/products/${productId}/stock-directions`) &&
        r.status() === 201,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  const fbsDirectionId = String(((await fbsCreateRes.json()) as { id: string }).id)
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 3 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 7')
  await expect(row.getByTestId(`seller-fbs-status-${productId}`)).toContainText(
    'Проверяем WB',
  )
  await expect(row.getByTestId(`seller-fbs-toggle-${productId}`)).toBeEnabled()
  await expect(row.getByTestId(`seller-fbs-cell-${productId}`)).not.toContainText('Лимит')
  await expect(row.locator(`[data-testid="seller-fbs-limit-${productId}"]`)).toHaveCount(0)
  const publicationGeometry = await row.evaluate((rowElement, targetProductId) => {
    const fbsCell = rowElement.querySelector(`[data-testid="seller-fbs-cell-${targetProductId}"]`)
    const table = rowElement.closest('table')
    const container = rowElement.closest('.MuiTableContainer-root')
    const doc = document.documentElement
    const body = document.body

    return {
      bodyScrollWidth: body.scrollWidth,
      documentScrollWidth: doc.scrollWidth,
      fbsCellText: fbsCell?.textContent ?? '',
      fbsLimitControls: rowElement.querySelectorAll('[data-testid^="seller-fbs-limit-"]').length,
      rowHeight: rowElement.getBoundingClientRect().height,
      tableScrollWidth: table?.scrollWidth ?? 0,
      tableContainerClientWidth: container?.clientWidth ?? 0,
      tableContainerScrollWidth: container?.scrollWidth ?? 0,
      viewportWidth: window.innerWidth,
    }
  }, productId)
  expect(publicationGeometry.fbsCellText).not.toContain('Лимит')
  expect(publicationGeometry.fbsLimitControls).toBe(0)
  expect(publicationGeometry.rowHeight).toBeLessThanOrEqual(72)
  expect(publicationGeometry.documentScrollWidth).toBeLessThanOrEqual(
    publicationGeometry.viewportWidth + 1,
  )
  expect(publicationGeometry.bodyScrollWidth).toBeLessThanOrEqual(
    publicationGeometry.viewportWidth + 1,
  )
  expect(publicationGeometry.tableScrollWidth).toBeLessThanOrEqual(
    publicationGeometry.tableContainerClientWidth + 1,
  )
  expect(publicationGeometry.tableContainerScrollWidth).toBeLessThanOrEqual(
    publicationGeometry.tableContainerClientWidth + 1,
  )
  expect(publicationGeometry.tableContainerClientWidth).toBeLessThanOrEqual(
    publicationGeometry.viewportWidth,
  )
  await expect(panel.getByTestId(`seller-stock-direction-row-${fbsDirectionId}`)).toContainText(
    'FBS-пул · 3 шт',
  )

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Набор сентябрь')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('2')
  const [reserveCreateRes] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/api/products/${productId}/stock-directions`) &&
        r.status() === 201,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  const reserveDirectionId = String(((await reserveCreateRes.json()) as { id: string }).id)
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'резервы 2 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 5')
  await expect(panel).toContainText('FBS-пул')
  await expect(panel).toContainText('Резерв/набор')
  await expect(panel.locator('[data-testid^="seller-stock-direction-row-"]')).toHaveCount(2)

  await page.getByTestId(`seller-stock-direction-edit-${reserveDirectionId}`).click()
  await expect(panel).toContainText('Редактировать направление')
  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Набор сентябрь long comment')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('4')
  await page
    .getByTestId(`seller-stock-direction-comment-${productId}`)
    .fill('Длинный комментарий не должен раздувать таблицу товаров')
  const [reservePatchRes] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/api/products/stock-directions/${reserveDirectionId}`) &&
        r.status() === 200,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  expect(String(((await reservePatchRes.json()) as { id: string }).id)).toBe(reserveDirectionId)
  await expect(panel.getByTestId(`seller-stock-direction-row-${reserveDirectionId}`)).toContainText(
    'Резерв/набор · 4 шт',
  )
  await expect(panel.locator('[data-testid^="seller-stock-direction-row-"]')).toHaveCount(2)
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'резервы 4 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 3')

  await page.getByTestId(`seller-stock-direction-edit-${reserveDirectionId}`).click()
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/api/products/stock-directions/${reserveDirectionId}`) &&
        r.status() === 200,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await expect(panel.getByTestId(`seller-stock-direction-row-${reserveDirectionId}`)).toContainText(
    'FBS-пул · 4 шт',
  )
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 7 шт',
  )
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'резервы 0 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 3')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Слишком много')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('4')
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/api/products/${productId}/stock-directions`) &&
        r.status() === 422,
    ),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await expect(page.getByTestId('seller-products-error')).toContainText(
    'Нельзя распределить больше, чем есть на ФФ',
  )
  await expect(page.getByTestId('seller-products-error')).not.toContainText(
    'directions_exceed_stock',
  )

  let deleteRequests = 0
  page.on('request', (request) => {
    if (
      request.method() === 'DELETE' &&
      request.url().includes(`/api/products/stock-directions/${fbsDirectionId}`)
    ) {
      deleteRequests += 1
    }
  })
  await page.getByTestId(`seller-stock-direction-delete-${fbsDirectionId}`).click()
  const deleteDialog = page.getByTestId('seller-stock-direction-delete-dialog')
  await expect(deleteDialog).toBeVisible()
  await expect(deleteDialog).toContainText('FBS WB')
  await expect(deleteDialog).toContainText('3 шт')
  await deleteDialog.getByRole('button', { name: 'Отмена' }).click()
  expect(deleteRequests).toBe(0)
  await expect(panel.getByTestId(`seller-stock-direction-row-${fbsDirectionId}`)).toBeVisible()

  await page.getByTestId(`seller-stock-direction-delete-${fbsDirectionId}`).click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes(`/api/products/stock-directions/${fbsDirectionId}`) &&
        r.status() === 204,
    ),
    page.getByTestId('seller-stock-direction-confirm-delete').click(),
  ])
  expect(deleteRequests).toBe(1)
  await expect(panel.getByTestId(`seller-stock-direction-row-${fbsDirectionId}`)).toHaveCount(0)
  await expect(row.getByTestId(`seller-stock-distribution-${productId}`)).toContainText(
    'FBS 4 шт',
  )
  await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 6')
})
