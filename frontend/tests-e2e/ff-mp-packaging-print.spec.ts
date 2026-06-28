import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { setWmsDateField } from './wms-date-field-helpers'

// TC-NEW-MP-016 — MP-021…023: иконка печати на вкладке «Упаковка» → MarkingPrintDialog; без ЧЗ — только количество ШК ВБ.
test('MP packaging: print icon opens qty-only dialog for non-marked product', async ({
  page,
}) => {
  test.setTimeout(120_000)

  const adminEmail = `e2e-mp-print-${Date.now()}@example.com`
  const sellerEmail = `e2e-mp-print-sl-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'
  const sku = `SKU-MP-PR-${Date.now()}`
  const planQty = 3

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Print')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Print', code: `wh-pr-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Print Brand' }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  await page.request.patch(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: auth,
    data: JSON.stringify({
      content_api_token: 'e2e-content',
      supplies_api_token: 'e2e-supplies',
    }),
  })

  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: auth,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId }),
  })
  const jobId = String(((await jobRes.json()) as { id: string }).id)
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, {
        headers: auth,
      })
      return (await jr.json()) as { status: string }
    })
    .toMatchObject({ status: 'done' })

  await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  })

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'MP Print Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'PR-LOC' }),
  })
  const locId = String(((await locRes.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: planQty,
      storage_location_id: locId,
    }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  const primIn = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primInBody = (await primIn.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, primInBody.boxes, barcode, [
    planQty,
  ])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await loginAsSeller(page, sellerEmail, password, { firstTime: true })
  await page.getByTestId('seller-create-mp-unload').click()
  await expect(page.getByTestId('seller-mp-unload-dialog')).toBeVisible()

  await page.getByLabel('Склад WB (маркетплейс)').click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByRole('option', { name: /E2E WB склад/ }).click(),
  ])
  await page
    .locator('[role="presentation"].MuiMenu-root')
    .first()
    .waitFor({ state: 'hidden', timeout: 5000 })
    .catch(() => undefined)

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    setWmsDateField(page, 'seller-mp-planned-date', '2026-06-20'),
  ])

  await page.getByTestId('seller-mp-add-products').click()
  await expect(page.getByTestId('seller-mp-picker')).toBeVisible()
  await page.getByTestId('seller-mp-picker-search').fill(sku)
  await expect(page.getByTestId('seller-mp-picker-qty').first()).toBeVisible({ timeout: 15000 })
  await page.getByTestId('seller-mp-picker-qty').first().fill(String(planQty))
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.url().includes('/lines') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('seller-mp-picker-apply').click(),
  ])
  await expect(page.getByTestId('seller-mp-lines-table')).toContainText(sku)

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marketplace-unload-requests/') &&
        r.url().includes('/plan') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('seller-mp-plan').click(),
  ])
  await expect(page.getByTestId('seller-mp-unload-dialog')).toContainText('Запланировано')
  await page.getByTestId('seller-mp-close').click()

  await page.goto('/')
  await page.getByTestId('nav-ff-mp-shipments').click()
  await page.locator('[data-doc-kind="marketplace_unload"]').first().click()
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()

  await expect(
    page.getByTestId('ff-supplies-doc-dialog').getByTestId(/^ff-mp-line-print-/),
  ).toHaveCount(0)

  await Promise.all([
    waitForPostOk(
      page,
      '/api/operations/marketplace-unload-requests',
      (u) => u.includes('/confirm'),
    ),
    page.getByTestId('ff-supplies-doc-submit').click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Утверждено')

  await page.getByTestId('ff-mp-tab-packaging').click()
  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible()

  const printBtn = page.getByTestId(/^ff-packaging-line-print-/).first()
  await expect(printBtn).toBeVisible()
  await printBtn.click()

  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await expect(page.getByTestId('product-barcode-print-dialog')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-preset-pairs')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-preset-label_only')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-custom-builder')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-preview')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-labels-per-product')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-wb-qty')).toBeVisible()

  await page.getByTestId('marking-print-wb-qty').locator('input').fill('6')
  await expect(page.getByTestId('marking-print-will-print')).toContainText('К печати: 6 этикеток')

  await page.getByTestId('marking-print-confirm').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden()
})
