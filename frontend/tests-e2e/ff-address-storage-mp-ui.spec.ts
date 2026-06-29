import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import {beginInboundReceivingWithBoxes,  fulfillInboundViaBoxScans } from './inbound-boxes-helpers'

// TC-NEW-MP-003 — TASK-003: при выкл. адресном хранении UI ячеек скрыт на отгрузке МП.
test('address storage off hides cell UI on marketplace unload', async ({ page }) => {
  const email = `e2e-mp-ui-cells-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP UI Cells')
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

  const patchOff = await page.request.patch(`${e2eApi}/tenant/settings`, {
    headers: auth,
    data: JSON.stringify({ address_storage_enabled: false }),
  })
  expect(patchOff.ok()).toBeTruthy()

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'W', code: `w-ui-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'UI Seller' }),
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
      name: 'UI Product',
      sku_code: `ui-sku-${Date.now()}`,
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

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'UI-LOC' }),
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
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    inboundId,
    { boxCount: 1 },
  )
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    inboundBoxes,
    barcode,
    [5],
  )
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 5 }),
  })
  await page.request.post(`${baseIn}/${sortInboundId}/submit`, { headers: auth })
  const { boxes: sortInboundBoxes } = await beginInboundReceivingWithBoxes(
    page.request,
    auth,
    sortInboundId,
    { boxCount: 1 },
  )
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    sortInboundId,
    sortInboundBoxes,
    barcode,
    [5],
  )
  await page.request.post(`${baseIn}/${sortInboundId}/verify`, { headers: auth })

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
    data: JSON.stringify({ product_id: productId, quantity: 1 }),
  })
  const confirmRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`,
    {
      headers: auth,
      data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
    },
  )
  expect(confirmRes.ok()).toBeTruthy()

  const pkgRes = await page.request.get(
    `${e2eApi}/operations/packaging-tasks/by-unload/${mid}`,
    { headers: auth },
  )
  expect(pkgRes.ok()).toBeTruthy()
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
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expect(page.getByTestId('ff-mp-active-location')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-start-picking')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-pick-scan-input')).toBeVisible()

  await page.getByTestId('ff-supplies-doc-close').click()

  await page.getByTestId('nav-ff-settings').click()
  const checkbox = page.getByRole('checkbox', { name: /Адресное хранение включено/i })
  const patchOn = waitForPatchOk(page, '/api/tenant/settings')
  const meOn = waitForGetOk(page, '/api/auth/me')
  await checkbox.check()
  await patchOn
  await meOn

  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  // TC-NEW-MP-005 — TASK-005: legacy «Начать подбор» удалён; сборка только через короба.
  await expect(page.getByTestId('ff-mp-start-picking')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-picking-dialog')).toHaveCount(0)
})
