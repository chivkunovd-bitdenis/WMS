import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'

// TC-NEW-MP-006 — TASK-011: модалка «Добавить товары» напротив короба; лимит по плану.
test('FF marketplace unload: box add-products modal respects plan limit', async ({ page }) => {
  const email = `e2e-mp-box-modal-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Box Modal')
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
    data: JSON.stringify({ name: 'W', code: `w-modal-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Modal Seller' }),
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
      name: 'Modal Product',
      sku_code: `modal-sku-${Date.now()}`,
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
    data: JSON.stringify({ code: 'MOD-LOC' }),
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
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    primInBody.boxes,
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
  const primSort = await page.request.post(`${baseIn}/${sortInboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primSortBody = (await primSort.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    sortInboundId,
    primSortBody.boxes,
    barcode,
    [5],
  )
  await page.request.post(`${baseIn}/${sortInboundId}/verify`, { headers: auth })

  const locList = await page.request.get(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
  })
  const locBarcode = String(
    ((await locList.json()) as { id: string; barcode: string }[]).find((x) => x.id === locId)
      ?.barcode,
  )
  expect(locBarcode).toBeTruthy()

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
    const packRes = await page.request.post(
      `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/lines/${pkgLine.id}/pack`,
      {
        headers: auth,
        data: JSON.stringify({ quantity: pkgLine.qty_need_pack }),
      },
    )
    expect(packRes.ok()).toBeTruthy()
  }
  const pkgComplete = await page.request.post(
    `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/complete`,
    { headers: auth, data: JSON.stringify({ acknowledge_all_packed: false }) },
  )
  expect(pkgComplete.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  const addBtn = page.locator('[data-testid^="ff-mp-box-add-products-"]')
  await expect(addBtn).toBeVisible()
  const addTestId = await addBtn.getAttribute('data-testid')
  const boxId = addTestId?.replace('ff-mp-box-add-products-', '') ?? ''
  expect(boxId.length).toBeGreaterThan(0)

  await addBtn.click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible()

  await page.getByTestId('ff-mp-box-add-scan-input').fill(locBarcode)
  await page.getByTestId('ff-mp-box-add-scan-submit').click()
  await expect(page.getByTestId('ff-mp-box-add-active-location')).toBeVisible()

  await expect(page.getByTestId(`ff-mp-box-add-row-${productId}`)).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId(`ff-mp-box-add-available-${productId}`)).toHaveText('3')

  await page.getByTestId(`ff-mp-box-add-qty-${productId}`).fill('2')
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${mid}/boxes/${boxId}/manual-line`,
    ),
    page.getByTestId(`ff-mp-box-add-manual-${productId}`).click(),
  ])
  // REV-FIX-018: success snackbar after add to box.
  await expect(page.getByTestId('ff-mp-box-add-success-snackbar')).toContainText('Добавлено 2 шт')
  await expect(page.getByTestId(`ff-mp-box-add-available-${productId}`)).toHaveText('1')
  await expect(page.getByTestId('ff-mp-open-box-lines')).toContainText('2')
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible()
  await expect(page.getByTestId(`ff-mp-box-add-manual-${productId}`)).toBeDisabled()

  const qtyInput = page.getByTestId(`ff-mp-box-add-qty-${productId}`)
  await qtyInput.fill('1')
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${mid}/boxes/${boxId}/manual-line`,
    ),
    page.getByTestId(`ff-mp-box-add-manual-${productId}`).click(),
  ])
  await expect(page.getByTestId(`ff-mp-box-add-available-${productId}`)).toHaveText('0')
  await expect(page.getByTestId(`ff-mp-box-add-manual-${productId}`)).toBeDisabled()
  await expect(page.getByTestId('ff-mp-open-box-lines')).toContainText('3')
})

// TC-NEW-MP-021 / MP-016: N≥2 batch-короба без завершённой упаковки; «Добавить товары» на втором коробе.
test('FF marketplace unload: batch three boxes add products on second box', async ({ page }) => {
  const email = `e2e-mp-batch3-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Batch3')
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
    data: JSON.stringify({ name: 'W', code: `w-batch3-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Batch3 Seller' }),
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
      name: 'Batch3 Product',
      sku_code: `batch3-sku-${Date.now()}`,
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
    data: JSON.stringify({ code: 'B3-LOC' }),
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
  const primSort = await page.request.post(`${baseIn}/${sortInboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primSortBody = (await primSort.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    sortInboundId,
    primSortBody.boxes,
    barcode,
    [5],
  )
  await page.request.post(`${baseIn}/${sortInboundId}/verify`, { headers: auth })

  const locList = await page.request.get(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
  })
  const locBarcode = String(
    ((await locList.json()) as { id: string; barcode: string }[]).find((x) => x.id === locId)
      ?.barcode,
  )
  expect(locBarcode).toBeTruthy()

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

  // MP-016: короба и модалка доступны параллельно с незавершённой упаковкой — не complete packaging.

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()

  await page.getByTestId('ff-mp-box-batch-count').locator('input').fill('3')
  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  const detailRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}`,
    { headers: auth },
  )
  const boxes = ((await detailRes.json()) as { boxes: { id: string }[] }).boxes
  expect(boxes.length).toBe(3)
  const secondBoxId = boxes[1].id

  await expect(page.getByTestId(`ff-mp-box-add-products-${secondBoxId}`)).toBeVisible()
  await expect(page.getByTestId(`ff-mp-box-add-products-${secondBoxId}`)).toBeEnabled()

  await page.getByTestId(`ff-mp-box-add-products-${secondBoxId}`).click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible()

  await page.getByTestId('ff-mp-box-add-scan-input').fill(locBarcode)
  await page.getByTestId('ff-mp-box-add-scan-submit').click()
  await expect(page.getByTestId('ff-mp-box-add-active-location')).toBeVisible()
  await expect(page.getByTestId(`ff-mp-box-add-row-${productId}`)).toBeVisible({ timeout: 15000 })

  await page.getByTestId(`ff-mp-box-add-qty-${productId}`).fill('2')
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${mid}/boxes/${secondBoxId}/manual-line`,
    ),
    page.getByTestId(`ff-mp-box-add-manual-${productId}`).click(),
  ])

  await expect(page.getByTestId(`ff-mp-box-lines-${secondBoxId}`)).toContainText('2')
  await page.getByTestId('ff-mp-box-add-close').click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).not.toBeVisible()
})

// TC-NEW-MP-022 — REV-FIX-009: два batch create по 1 коробу; оба с «Добавить товары».
test('FF marketplace unload: two single-box batch creates both allow add products', async ({
  page,
}) => {
  const email = `e2e-mp-batch1x2-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Batch1x2')
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
    data: JSON.stringify({ name: 'W', code: `w-b1x2-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Batch1x2 Seller' }),
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
      name: 'Batch1x2 Product',
      sku_code: `b1x2-sku-${Date.now()}`,
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
    data: JSON.stringify({ packaging_instructions: 'E2E batch1x2' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'B1X2-LOC' }),
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
  const primSort = await page.request.post(`${baseIn}/${sortInboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primSortBody = (await primSort.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    sortInboundId,
    primSortBody.boxes,
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
    const packRes = await page.request.post(
      `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/lines/${pkgLine.id}/pack`,
      {
        headers: auth,
        data: JSON.stringify({ quantity: pkgLine.qty_need_pack }),
      },
    )
    expect(packRes.ok()).toBeTruthy()
  }
  const pkgComplete = await page.request.post(
    `${e2eApi}/operations/packaging-tasks/${pkgBody.id}/complete`,
    { headers: auth, data: JSON.stringify({ acknowledge_all_packed: false }) },
  )
  expect(pkgComplete.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expect(page.getByTestId('ff-mp-box-batch-create')).toBeEnabled()

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])
  await expect(page.getByTestId('ff-mp-box-batch-create')).toBeEnabled()

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  const detailRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${mid}`,
    { headers: auth },
  )
  const boxes = ((await detailRes.json()) as { boxes: { id: string }[] }).boxes
  expect(boxes.length).toBe(2)

  for (const box of boxes) {
    await expect(page.getByTestId(`ff-mp-box-add-products-${box.id}`)).toBeVisible()
    await expect(page.getByTestId(`ff-mp-box-add-products-${box.id}`)).toBeEnabled()
  }
})

// TC-NEW-MP-018 — MP-018: ручной выбор ячейки + scan товара в модалке короба.
test('FF marketplace unload: box modal manual location and product scan', async ({ page }) => {
  const email = `e2e-mp018-${Date.now()}@example.com`
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP018')
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
    data: JSON.stringify({ name: 'W', code: `w-mp018-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'MP018 Seller' }),
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
      name: 'MP018 Product',
      sku_code: `mp018-sku-${Date.now()}`,
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
    data: JSON.stringify({ code: 'MP018-LOC' }),
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
  await fulfillInboundViaBoxScans(
    page.request,
    auth,
    inboundId,
    primInBody.boxes,
    barcode,
    [5],
  )
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
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${mid}`),
    waitForGetOk(page, '/api/operations/marketplace-unload-requests/'),
    page.locator('[data-doc-kind="marketplace_unload"]').first().click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()

  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${mid}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  const addBtn = page.locator('[data-testid^="ff-mp-box-add-products-"]')
  const addTestId = await addBtn.getAttribute('data-testid')
  const boxId = addTestId?.replace('ff-mp-box-add-products-', '') ?? ''
  await addBtn.click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible()

  await page.getByTestId('ff-mp-box-add-location-select').click()
  await page.getByRole('option', { name: 'MP018-LOC' }).click()
  await expect(page.getByTestId('ff-mp-box-add-active-location')).toContainText('MP018-LOC')

  await page.getByTestId('ff-mp-box-add-scan-input').fill(barcode)
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${mid}/boxes/${boxId}/scan`,
    ),
    page.getByTestId('ff-mp-box-add-scan-submit').click(),
  ])
  await expect(page.getByTestId('ff-mp-box-add-success-snackbar')).toContainText('Добавлено 1 шт')
  await expect(page.getByTestId(`ff-mp-box-add-available-${productId}`)).toHaveText('2')
  await expect(page.getByTestId('ff-mp-open-box-lines')).toContainText('1')
})
