import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'

// TC-NEW-MP-006 / MP-005: короба доступны до завершения упаковки.
test('FF marketplace unload: box create enabled before packaging done', async ({ page }) => {
  const email = `e2e-mp-pkg-gate-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Pkg Gate')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token).toBeTruthy()
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'W', code: `w-pkg-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Gate Seller' }),
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

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Gate Product',
      sku_code: `gate-sku-${Date.now()}`,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  await page.request.post(`${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, nm_id: 424242 }),
  })

  await page.request.patch(`${e2eApi}/products/${productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ packaging_instructions: 'E2E gate packaging' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'GATE-LOC' }),
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
      expected_qty: 5,
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
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, primInBody.boxes, barcode, [5])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  const whs = await page.request.get(`${e2eApi}/operations/wb-mp-warehouses`, { headers: auth })
  const wbWid = Number(((await whs.json()) as { wb_warehouse_id: number }[])[0].wb_warehouse_id)

  const mu = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({
      warehouse_id: whId,
      seller_id: sellerId,
      wb_mp_warehouse_id: wbWid,
    }),
  })
  const mid = String(((await mu.json()) as { id: string }).id)
  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, quantity: 2 }),
  })
  await page.request.post(`${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`, {
    headers: auth,
    data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
  })

  const boxOk = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/boxes`,
    { headers: auth, data: JSON.stringify({ box_preset: '60_40_40' }) },
  )
  expect(boxOk.status()).toBe(201)

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-packaging-gate-alert')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-packaging-progress')).toBeVisible()
  await expect(page.getByTestId('ff-mp-box-batch-create')).toBeEnabled()

  await page.getByTestId('ff-mp-tab-final').click()
  await expect(page.getByTestId('ff-mp-tab-final-panel')).toBeVisible()
  await expect(page.getByTestId('ff-mp-ship')).toBeDisabled()
})
