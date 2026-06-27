import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'

// TC-NEW-MP-007 — TASK-012: вкладки документа отгрузки на МП без потери контекста.
test('FF marketplace unload: tabs switch without losing document context', async ({ page }) => {
  const email = `e2e-mp-tabs-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Tabs')
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
    data: JSON.stringify({ name: 'W', code: `w-tabs-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Tabs Seller' }),
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
      name: 'Tabs Product',
      sku_code: `tabs-sku-${Date.now()}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E tabs' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'TABS-LOC' }),
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

  const pkgRes = await page.request.get(
    `${e2eApi}/operations/packaging-tasks/by-unload/${mid}`,
    { headers: auth },
  )
  const pkgBody = (await pkgRes.json()) as {
    id: string
    lines: { id: string; qty_need_pack: number }[]
  }
  const pkgLine = pkgBody.lines[0]
  if (pkgLine && pkgLine.qty_need_pack > 0) {
    await page.request.post(
      `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/lines/${pkgLine.id}/pack`,
      {
        headers: auth,
        data: JSON.stringify({ quantity: pkgLine.qty_need_pack }),
      },
    )
  }
  await page.request.post(
    `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/complete`,
    { headers: auth, data: JSON.stringify({ acknowledge_all_packed: false }) },
  )

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  // REV-FIX-011: page description must not mention legacy «подбор по ячейкам».
  await expect(page.getByTestId('ff-mp-shipments-page')).not.toContainText(/подбор по ячейкам/i)
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-tab-products')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()

  await expect(page.getByTestId('ff-mp-collect-summary-planned')).toHaveText('2')
  await expect(page.getByTestId('ff-mp-collect-summary-distributed')).toHaveText('0')
  await expect(page.getByTestId('ff-mp-collect-summary-remaining')).toHaveText('2')
  await expect(page.getByTestId('ff-mp-collect-warning')).toBeVisible()
  await expect(page.getByTestId('ff-mp-collect-summary-packaging')).toBeVisible()

  await page.getByTestId('ff-mp-tab-products').click()
  await expect(page.getByTestId('ff-supplies-doc-lines')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toHaveCount(0)

  await page.getByTestId('ff-mp-tab-packaging').click()
  await expect(page.getByTestId('ff-mp-tab-packaging-panel')).toBeVisible()

  await page.getByTestId('ff-mp-tab-final').click()
  await expect(page.getByTestId('ff-mp-tab-final-panel')).toBeVisible()
  await expect(page.getByTestId('ff-mp-ship')).toBeDisabled()

  await page.getByTestId('ff-mp-tab-boxes').click()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expect(page.getByTestId('ff-mp-unload-document-number')).toBeVisible()
})

// TC-NEW-MP-007 / REV-FIX-006: вкладка «Упаковка» доступна на черновике при linked_packaging_task.
test('FF marketplace unload: packaging tab enabled on draft', async ({ page }) => {
  const email = `e2e-mp-draft-pkg-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Draft Pkg')
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
    data: JSON.stringify({ name: 'W', code: `w-dpkg-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Draft Pkg Seller' }),
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
      name: 'Draft Pkg Product',
      sku_code: `dpkg-sku-${Date.now()}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E draft pkg' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'DPKG-LOC' }),
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

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  // REV-FIX-013: plan total visible on draft «Товары» tab.
  await expect(page.getByTestId('ff-mp-plan-total')).toContainText('2')
  await expect(page.getByTestId('ff-mp-tab-packaging')).toBeEnabled()
  // REV-FIX-008: packaging progress visible on draft when linked_packaging_task exists.
  await expect(page.getByTestId('ff-mp-packaging-progress')).toBeVisible()

  await page.getByTestId('ff-mp-tab-packaging').click()
  await expect(page.getByTestId('ff-mp-tab-packaging-panel')).toBeVisible()
  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible()
  await expect(page.getByTestId('ff-mp-tab-boxes')).toBeDisabled()
  // REV-FIX-007: no misleading copy that packaging appears only after confirm.
  await expect(page.getByTestId('ff-mp-tab-packaging-panel')).not.toContainText(
    /после подтверждения/i,
  )
})
