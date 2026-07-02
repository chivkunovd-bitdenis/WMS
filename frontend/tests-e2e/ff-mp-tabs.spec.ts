import { test, expect } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

const MP_SELLER_NAME_TABS = 'Tabs Seller'
const MP_SELLER_NAME_DRAFT_PKG = 'Draft Pkg Seller'
const MP_SELLER_NAME_MAIN_SCAN = 'Main Scan Seller'
const MP_SELLER_NAME_OUT_FE_02 = 'OUT FE 02 Seller'

function mpUnloadListRow(page: Page, sellerName: string) {
  return page.getByTestId('ff-docs-row').filter({ hasText: sellerName })
}

function visibleDocumentNumber(body: {
  display_number?: string | null
  document_number?: string | null
}): string {
  if (body.display_number?.trim()) {
    return body.display_number.trim()
  }
  const counter = body.document_number?.match(/(\d+)\s*$/)?.[1]
  if (counter) {
    return `№${counter.padStart(6, '0')}`
  }
  return body.document_number ?? ''
}

async function openMpUnloadFromList(
  page: Page,
  unloadId: string,
  sellerName: string,
): Promise<{ displayNumber: string; technicalNumber: string }> {
  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token).toBeTruthy()
  const unloadRes = await page.request.get(`/api/operations/marketplace-unload-requests/${unloadId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(unloadRes.ok(), await unloadRes.text()).toBeTruthy()
  const unloadBody = (await unloadRes.json()) as {
    document_number: string | null
    display_number: string | null
  }
  const displayNumber = visibleDocumentNumber(unloadBody)
  const technicalNumber = unloadBody.document_number ?? ''
  expect(displayNumber).toBeTruthy()

  const row = mpUnloadListRow(page, sellerName).filter({
    hasText: displayNumber,
  })
  await expect(row).toHaveCount(1)
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${unloadId}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    row.click(),
  ])

  return { displayNumber, technicalNumber }
}

async function expectMpTabSelected(page: Page, tabTestId: string): Promise<void> {
  await expect(page.getByTestId(tabTestId)).toHaveAttribute('aria-selected', 'true')
}

function formatDisplayDocumentNumber(documentNumber: string): string {
  const counter = documentNumber.match(/(\d+)\s*$/)?.[1]
  expect(counter).toBeTruthy()
  return `№${counter!.padStart(6, '0')}`
}

async function postInboundLineToSorting(
  req: APIRequestContext,
  auth: { Authorization: string },
  baseIn: string,
  inboundId: string,
  lineId: string,
  qty: number,
): Promise<void> {
  const patchActual = await req.patch(`${baseIn}/${inboundId}/lines/${lineId}/actual`, {
    headers: { ...auth, 'Content-Type': 'application/json' },
    data: JSON.stringify({ actual_qty: qty }),
  })
  expect(patchActual.ok(), await patchActual.text()).toBeTruthy()
  const verifyRes = await req.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  expect(verifyRes.ok(), await verifyRes.text()).toBeTruthy()
}

async function postInboundLineToStorage(
  req: APIRequestContext,
  auth: { Authorization: string },
  baseIn: string,
  inboundId: string,
  lineId: string,
  qty: number,
): Promise<void> {
  const patchActual = await req.patch(`${baseIn}/${inboundId}/lines/${lineId}/actual`, {
    headers: { ...auth, 'Content-Type': 'application/json' },
    data: JSON.stringify({ actual_qty: qty }),
  })
  expect(patchActual.ok(), await patchActual.text()).toBeTruthy()
  const verifyRes = await req.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  expect(verifyRes.ok(), await verifyRes.text()).toBeTruthy()
  const receiveRes = await req.post(`${baseIn}/${inboundId}/lines/${lineId}/receive`, {
    headers: { ...auth, 'Content-Type': 'application/json' },
    data: JSON.stringify({ quantity: qty }),
  })
  expect(receiveRes.ok(), await receiveRes.text()).toBeTruthy()
}

// TC-NEW-MP-007 — TASK-012: вкладки документа отгрузки на МП без потери контекста.
test('FF marketplace unload: tabs switch without losing document context', async ({ page }) => {
  const email = `e2e-mp-tabs-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

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
    data: JSON.stringify({ name: MP_SELLER_NAME_TABS }),
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
  const locLineRes = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 5,
      storage_location_id: locId,
    }),
  })
  expect(locLineRes.ok()).toBeTruthy()
  const locLineId = String(((await locLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  await postInboundLineToStorage(page.request, auth, baseIn, inboundId, locLineId, 5)

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id)
  const sortLineRes = await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 5 }),
  })
  expect(sortLineRes.ok()).toBeTruthy()
  const sortLineId = String(((await sortLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${sortInboundId}/submit`, { headers: auth })
  await postInboundLineToSorting(page.request, auth, baseIn, sortInboundId, sortLineId, 5)

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
  expect(pkgRes.ok()).toBeTruthy()
  const pkgBody = (await pkgRes.json()) as {
    id: string
    lines: { id: string; qty_need_pack: number }[]
  }
  const pkgLine = pkgBody.lines[0]
  expect(pkgLine?.id).toBeTruthy()
  if (pkgLine && pkgLine.qty_need_pack > 0) {
    await page.request.post(
      `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/lines/${pkgLine.id}/pack`,
      {
        headers: auth,
        data: JSON.stringify({ quantity: pkgLine.qty_need_pack }),
      },
    )
  }
  const pkgComplete = await page.request.post(
    `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/complete`,
    { headers: auth, data: JSON.stringify({ acknowledge_all_packed: false }) },
  )
  expect(pkgComplete.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  // REV-FIX-011: page description must not mention legacy «подбор по ячейкам».
  await expect(page.getByTestId('ff-mp-shipments-page')).not.toContainText(/подбор по ячейкам/i)
  const { displayNumber: unloadDisplayNumber, technicalNumber: unloadDocumentNumber } =
    await openMpUnloadFromList(page, mid, MP_SELLER_NAME_TABS)

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-unload-document-number')).toHaveText(
    `Отгрузка ${unloadDisplayNumber}`,
  )
  await expect(page.getByTestId('ff-supplies-doc-dialog')).not.toContainText(unloadDocumentNumber)
  await expect(page.getByTestId('ff-mp-tab-products')).toBeVisible()
  await expect(page.getByTestId('ff-mp-tab-boxes')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-tab-final')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expectMpTabSelected(page, 'ff-mp-tab-products')
  await expect(page.getByTestId('ff-mp-ship')).toBeDisabled()

  await expect(page.getByTestId('ff-mp-shipment-summary')).toBeVisible()
  await expect(page.getByTestId('ff-mp-shipment-summary-planned')).toHaveText('2')
  await expect(page.getByTestId('ff-mp-shipment-summary-distributed')).toHaveText('0')
  await expect(page.getByTestId('ff-mp-shipment-summary-remaining')).toHaveText('2')
  await expect(page.getByTestId('ff-mp-shipment-summary-remaining')).toHaveCSS(
    'color',
    'rgb(237, 108, 2)',
  )
  await expect(page.getByTestId('ff-mp-shipment-summary-packed')).toHaveText('2/2')

  await page.getByTestId('ff-mp-tab-packaging').click()
  await expect(page.getByTestId('ff-mp-tab-packaging-panel')).toBeVisible()
  await expectMpTabSelected(page, 'ff-mp-tab-packaging')
  await expect(page.getByTestId('ff-mp-boxes')).toHaveCount(0)

  await page.getByTestId('ff-mp-tab-products').click()
  await expect(page.getByTestId('ff-supplies-doc-lines')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expectMpTabSelected(page, 'ff-mp-tab-products')
  await expect(page.getByTestId('ff-mp-ship')).toBeDisabled()
  await expect(page.getByTestId('ff-mp-unload-document-number')).toHaveText(
    `Отгрузка ${unloadDisplayNumber}`,
  )
})

// TC-NEW-MP-011 / MP-012: на черновике нет плашки прогресса упаковки.
test('FF marketplace unload: no packaging progress banner on draft', async ({ page }) => {
  const email = `e2e-mp-draft-pkg-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

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
    data: JSON.stringify({ name: MP_SELLER_NAME_DRAFT_PKG }),
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
  const locLineRes = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 5,
      storage_location_id: locId,
    }),
  })
  expect(locLineRes.ok()).toBeTruthy()
  const locLineId = String(((await locLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  await postInboundLineToStorage(page.request, auth, baseIn, inboundId, locLineId, 5)

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id)
  const sortLineRes = await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 5 }),
  })
  expect(sortLineRes.ok()).toBeTruthy()
  const sortLineId = String(((await sortLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${sortInboundId}/submit`, { headers: auth })
  await postInboundLineToSorting(page.request, auth, baseIn, sortInboundId, sortLineId, 5)

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
  const lineRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/lines`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: productId, quantity: 2 }),
    },
  )
  expect(lineRes.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await openMpUnloadFromList(page, mid, MP_SELLER_NAME_DRAFT_PKG)

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expectMpTabSelected(page, 'ff-mp-tab-products')
  // MP-014: дата и склад в шапке документа.
  await expect(page.getByTestId('ff-mp-doc-header-fields')).toBeVisible()
  await expect(page.getByTestId('ff-mp-planned-date')).toBeVisible()
  await expect(page.getByTestId('ff-mp-ff-warehouse-name')).toBeVisible()
  await expect(page.getByTestId('ff-mp-shipment-summary')).toBeVisible()
  await expect(page.getByTestId('ff-mp-shipment-summary-planned')).toHaveText('2')
  await expect(page.getByTestId('ff-mp-shipment-summary-packed')).toHaveText('—')
  await expect(page.getByTestId('ff-mp-tab-packaging')).toBeDisabled()
  await expect(page.getByTestId('ff-mp-tab-boxes')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-tab-final')).toHaveCount(0)
})

// TC-NEW-MP-015 — MP-020: главный scan на «Товарах» не принимает штрихкод товара.
test('FF marketplace unload: main scan rejects product barcode', async ({ page }) => {
  const email = `e2e-mp-mainscan-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Main Scan')
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
    data: JSON.stringify({ name: 'W', code: `w-mainscan-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: MP_SELLER_NAME_MAIN_SCAN }),
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
      name: 'Main Scan Product',
      sku_code: `mainscan-sku-${Date.now()}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E: пакет' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'MAIN-LOC' }),
  })
  const locId = String(((await locRes.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  const locLineRes = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 5,
      storage_location_id: locId,
    }),
  })
  expect(locLineRes.ok()).toBeTruthy()
  const locLineId = String(((await locLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  await postInboundLineToStorage(page.request, auth, baseIn, inboundId, locLineId, 5)

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id)
  const sortLineRes = await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 5 }),
  })
  expect(sortLineRes.ok()).toBeTruthy()
  const sortLineId = String(((await sortLineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${sortInboundId}/submit`, { headers: auth })
  await postInboundLineToSorting(page.request, auth, baseIn, sortInboundId, sortLineId, 5)

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
    data: JSON.stringify({ product_id: productId, quantity: 3 }),
  })
  const confirmRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`,
    {
      headers: auth,
      data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
    },
  )
  expect(confirmRes.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await openMpUnloadFromList(page, mid, MP_SELLER_NAME_MAIN_SCAN)
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expectMpTabSelected(page, 'ff-mp-tab-products')

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  await page.getByTestId('ff-mp-pick-scan-input').fill(barcode)
  await page.getByTestId('ff-mp-pick-scan').click()
  await expect(page.getByTestId('ff-mp-modal-error')).toContainText('Добавить товары')
  await expect(page.getByTestId('ff-mp-attach-box-dialog')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-shipment-summary-distributed')).toHaveText('0')
})

// TC-NEW-OUT-FE-02 — OUT-FE-02: confirmed unload product table — no early red rows; qty columns aligned.
test('TC-NEW-OUT-FE-02: shipment table columns no early red', async ({ page }) => {
  const email = `e2e-out-fe-02-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E OUT FE 02')
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
    data: JSON.stringify({ name: 'W', code: `w-outfe02-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: MP_SELLER_NAME_OUT_FE_02 }),
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
      name: 'OUT FE 02 Product',
      sku_code: `outfe02-sku-${Date.now()}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E out fe 02' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'OUTFE02-LOC' }),
  })
  const locId = String(((await locRes.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  const lineRes = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 5,
      storage_location_id: locId,
    }),
  })
  expect(lineRes.ok()).toBeTruthy()
  const lineId = String(((await lineRes.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  await postInboundLineToStorage(page.request, auth, baseIn, inboundId, lineId, 5)

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
  const confirmRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}/confirm`,
    {
      headers: auth,
      data: JSON.stringify({ planned_shipment_date: '2026-06-01' }),
    },
  )
  expect(confirmRes.ok(), await confirmRes.text()).toBeTruthy()

  const unloadDetailRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}`,
    { headers: auth },
  )
  expect(unloadDetailRes.ok()).toBeTruthy()
  const mpLineId = String(
    ((await unloadDetailRes.json()) as { lines: { id: string }[] }).lines[0].id,
  )

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await openMpUnloadFromList(page, mid, MP_SELLER_NAME_OUT_FE_02)

  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await page.getByTestId('ff-mp-tab-products').click()
  await expectMpTabSelected(page, 'ff-mp-tab-products')
  await expect(page.getByTestId('ff-supplies-doc-lines')).toBeVisible()
  await expect(page.locator('[data-testid^="ff-mp-line-discrepancy-"]')).toHaveCount(0)
  await expect(page.getByTestId(`ff-mp-line-row-${mpLineId}`)).toBeVisible()
  await expect(page.getByTestId(`ff-mp-line-plan-${mpLineId}`)).toHaveText('2')
  await expect(page.getByTestId(`ff-mp-line-picked-${mpLineId}`)).toHaveText('0')
  await expect(page.getByTestId(`ff-mp-line-remaining-${mpLineId}`)).toHaveText('2')
  await expect(page.getByTestId('ff-mp-print-actions')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expect(page.getByTestId('ff-mp-ship')).toBeDisabled()
})
