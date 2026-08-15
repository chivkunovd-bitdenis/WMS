import { test, expect, type Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'
import { beginInboundReceivingWithBoxes, fulfillInboundViaBoxScans } from './inbound-boxes-helpers'

const PLAN_QTY = 4
const QTY_PER_BOX = 2

async function addProductsToBoxViaModal(
  page: Page,
  requestId: string,
  boxId: string,
  locBarcode: string,
  productId: string,
  qty: number,
): Promise<void> {
  await page.getByTestId(`ff-mp-box-add-products-${boxId}`).click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).toBeVisible()

  await page.getByTestId('ff-mp-box-add-scan-input').fill(locBarcode)
  await page.getByTestId('ff-mp-box-add-scan-submit').click()
  await expect(page.getByTestId('ff-mp-box-add-active-location')).toBeVisible()
  await expect(page.getByTestId(`ff-mp-box-add-row-${productId}`)).toBeVisible({
    timeout: 15000,
  })

  await page.getByTestId(`ff-mp-box-add-qty-${productId}`).fill(String(qty))
  await Promise.all([
    waitForPostOk(
      page,
      `/api/operations/marketplace-unload-requests/${requestId}/boxes/${boxId}/manual-line`,
    ),
    page.getByTestId(`ff-mp-box-add-manual-${productId}`).click(),
  ])
  await expect(page.getByTestId('ff-mp-box-add-success-snackbar')).toContainText(
    `Добавлено ${qty} шт`,
  )
  await page.getByTestId('ff-mp-box-add-close').click()
  await expect(page.getByTestId('ff-mp-box-add-dialog')).not.toBeVisible()
}

async function openFfMpDocument(page: Page, requestId: string): Promise<void> {
  await Promise.all([
    waitForGetOk(page, `/api/operations/marketplace-unload-requests/${requestId}`),
    page.goto(`/app/ff/mp-shipments?open_mp=${requestId}`),
  ])
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toBeVisible()
}

async function expectMpBoxOperationalControlsEnabled(page: Page): Promise<void> {
  await expect(page.getByTestId('ff-mp-pick-scan-field')).toBeVisible()
  await expect(page.getByTestId('ff-mp-pick-scan')).toBeEnabled()
  await expect(page.getByTestId('ff-mp-box-batch-count')).toBeVisible()
  await expect(page.getByTestId('ff-mp-import-boxes')).toBeEnabled()
  await expect(page.getByTestId('ff-mp-box-batch-create')).toBeEnabled()
}

async function expectMpBoxOperationalControlsHidden(page: Page): Promise<void> {
  await expect(page.getByTestId('ff-mp-pick-scan-field')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-pick-scan')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-box-batch-count')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-import-boxes')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-box-batch-create')).toHaveCount(0)
}

async function expectMpBoxDestructiveControlsHidden(
  page: Page,
  boxIds: string[] = [],
): Promise<void> {
  await expect(page.getByTestId('ff-mp-box-menu-copy')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-box-menu-delete')).toHaveCount(0)
  await expect(page.getByTestId(/^ff-mp-box-line-remove-/)).toHaveCount(0)

  for (const boxId of boxIds) {
    await expect(page.getByTestId(`ff-mp-box-menu-${boxId}`)).toHaveCount(0)
    await expect(page.getByTestId(`ff-mp-box-delete-${boxId}`)).toHaveCount(0)
  }
}

async function setSellerMpPlannedDate(page: Page, isoDate: string): Promise<void> {
  const [yearStr, monthStr, dayStr] = isoDate.split('-')
  const dateField = page.getByTestId('seller-mp-planned-date')
  await dateField.getByRole('spinbutton', { name: 'Day' }).fill(dayStr)
  await dateField.getByRole('spinbutton', { name: 'Month' }).fill(monthStr)
  await dateField.getByRole('spinbutton', { name: 'Year' }).fill(yearStr)
  await dateField.getByRole('spinbutton', { name: 'Year' }).blur()
}

// TC-NEW-MP-FULL-001 — MP-032: seller plan → FF confirm → boxes ∥ packaging → ship from footer.
test('MP unload full flow: parallel boxes then packaging then ship', async ({ page }) => {
  test.setTimeout(180_000)

  const adminEmail = `e2e-mp-full-${Date.now()}@example.com`
  const sellerEmail = `e2e-mp-full-sl-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const barcode = 'E2E-MOCK-BARCODE'
  const sku = `SKU-FULL-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E MP Full Flow')
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
    data: JSON.stringify({ name: 'WH', code: `wh-full-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'Full Flow Brand' }),
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

  const accRes = await page.request.post(`${e2eApi}/auth/seller-accounts`, {
    headers: auth,
    data: JSON.stringify({ seller_id: sellerId, email: sellerEmail }),
  })
  expect(accRes.ok()).toBeTruthy()

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Full Flow Product',
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

  await page.request.patch(`${e2eApi}/products/${productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ packaging_instructions: 'E2E: пакет + стикер WB' }),
  })

  const locRes = await page.request.post(`${e2eApi}/warehouses/${whId}/locations`, {
    headers: auth,
    data: JSON.stringify({ code: 'FULL-LOC' }),
  })
  const locId = String(((await locRes.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId, planned_box_count: 1 }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({
      product_id: productId,
      expected_qty: 10,
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
    [10],
  )
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  const inboundSort = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId, planned_box_count: 1 }),
  })
  const sortInboundId = String(((await inboundSort.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${sortInboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 10 }),
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
    [10],
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

  const ffDraftRes = await page.request.post(`${e2eApi}/operations/marketplace-unload-requests`, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId, seller_id: sellerId }),
  })
  const ffDraftId = String(((await ffDraftRes.json()) as { id: string }).id)
  const ffDraftLineRes = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests/${ffDraftId}/lines`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: productId, quantity: 1 }),
    },
  )
  const ffDraftLineId = String(((await ffDraftLineRes.json()) as { id: string }).id)

  await openFfMpDocument(page, ffDraftId)
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Черновик')
  // TC-NEW-F15-DRAFT-DELETE — draft MP unload lines keep the FF delete affordance.
  await expect(page.getByTestId(`ff-supplies-line-delete-${ffDraftLineId}`)).toBeEnabled()
  await page.getByTestId('ff-supplies-doc-close').click()
  await expect(page.getByTestId('ff-supplies-doc-dialog')).not.toBeVisible()

  await loginAsSeller(page, sellerEmail, password, { firstTime: true })
  await expect(page.getByTestId('app-frame')).toBeVisible()

  await Promise.all([
    waitForPostOk(page, '/api/operations/marketplace-unload-requests/seller'),
    page.getByTestId('seller-create-mp-unload').click(),
  ])
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
    setSellerMpPlannedDate(page, '2026-06-15'),
  ])

  await page.getByTestId('seller-mp-add-products').click()
  await expect(page.getByTestId('seller-mp-picker')).toBeVisible()
  await page.getByTestId('seller-mp-picker-search').fill(sku)
  await page.getByTestId('seller-mp-picker-qty').first().fill(String(PLAN_QTY))
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

  let requestId = ''
  const [planRes] = await Promise.all([
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
  requestId = String(((await planRes.json()) as { id: string }).id)
  expect(requestId.length).toBeGreaterThan(0)

  await expect(page.getByTestId('seller-mp-unload-dialog')).toContainText('Запланировано')
  await page.getByTestId('seller-mp-close').click()

  await openFfMpDocument(page, requestId)
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Запланировано')
  // TC-NEW-F15-SUBMITTED-NO-DELETE — submitted seller MP unload must not expose false line delete.
  await expect(page.getByTestId(/^ff-supplies-line-delete-/)).toHaveCount(0)
  const submittedBeforeRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  const submittedBefore = (await submittedBeforeRes.json()) as {
    status: string
    lines: { id: string }[]
  }
  expect(submittedBefore.status).toBe('submitted')
  expect(submittedBefore.lines.length).toBe(1)
  const submittedLineId = String(submittedBefore.lines[0]?.id ?? '')
  expect(submittedLineId).toBeTruthy()
  const directDeleteSubmittedDoc = await page.request.delete(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  expect(directDeleteSubmittedDoc.status()).toBe(409)
  expect(((await directDeleteSubmittedDoc.json()) as { detail: string }).detail).toBe('not_draft')
  const directDeleteSubmittedLine = await page.request.delete(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}/lines/${submittedLineId}`,
    { headers: auth },
  )
  expect(directDeleteSubmittedLine.status()).toBe(409)
  expect(((await directDeleteSubmittedLine.json()) as { detail: string }).detail).toBe('not_draft')
  const submittedAfterRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  const submittedAfter = (await submittedAfterRes.json()) as {
    status: string
    lines: { id: string }[]
  }
  expect(submittedAfter.status).toBe('submitted')
  expect(submittedAfter.lines.map((ln) => ln.id)).toEqual([submittedLineId])

  await expect(page.getByTestId('ff-supplies-doc-submit')).toBeEnabled()
  await Promise.all([
    waitForPostOk(
      page,
      '/api/operations/marketplace-unload-requests',
      (u) => u.includes('/confirm'),
    ),
    page.getByTestId('ff-supplies-doc-submit').click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Утверждено')
  // TC-NEW-F15-CONFIRMED-NO-DELETE — confirmed MP unload is history: no line delete UI and direct DELETE is rejected.
  await expect(page.getByTestId(/^ff-supplies-line-delete-/)).toHaveCount(0)
  const confirmedBeforeRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  const confirmedBefore = (await confirmedBeforeRes.json()) as {
    status: string
    lines: { id: string }[]
  }
  expect(confirmedBefore.status).toBe('confirmed')
  expect(confirmedBefore.lines.length).toBe(1)
  const confirmedLineId = String(confirmedBefore.lines[0]?.id ?? '')
  expect(confirmedLineId).toBeTruthy()
  const directDeleteConfirmed = await page.request.delete(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}/lines/${confirmedLineId}`,
    { headers: auth },
  )
  expect(directDeleteConfirmed.status()).toBe(409)
  expect(((await directDeleteConfirmed.json()) as { detail: string }).detail).toBe('not_draft')
  const confirmedAfterRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  const confirmedAfter = (await confirmedAfterRes.json()) as {
    status: string
    lines: { id: string }[]
  }
  expect(confirmedAfter.status).toBe('confirmed')
  expect(confirmedAfter.lines.map((ln) => ln.id)).toEqual([confirmedLineId])

  // TC-NEW-F15-CONFIRMED-BOX-WORK — confirmed MP unload keeps box creation/filling UI inside Packaging but hides destructive controls.
  await page.getByTestId('ff-mp-tab-packaging').click()
  await expect(page.getByTestId('ff-mp-tab-packaging-panel')).toBeVisible()
  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible()
  await page.getByTestId('ff-mp-boxes-summary').click()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expectMpBoxOperationalControlsEnabled(page)
  await expectMpBoxDestructiveControlsHidden(page)
  await page.getByTestId('ff-mp-box-batch-count').locator('input').fill('2')
  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${requestId}/boxes/batch`),
    page.getByTestId('ff-mp-box-batch-create').click(),
  ])

  const detailRes = await page.request.get(
    `${e2eApi}/operations/marketplace-unload-requests/${requestId}`,
    { headers: auth },
  )
  const detail = (await detailRes.json()) as { boxes: { id: string }[] }
  expect(detail.boxes.length).toBe(2)

  for (const box of detail.boxes) {
    await expect(page.getByTestId(`ff-mp-box-row-${box.id}`)).toBeVisible()
    await expect(page.getByTestId(`ff-mp-box-add-products-${box.id}`)).toBeEnabled()
  }
  await expectMpBoxDestructiveControlsHidden(
    page,
    detail.boxes.map((box) => box.id),
  )
  await addProductsToBoxViaModal(page, requestId, detail.boxes[0].id, locBarcode, productId, QTY_PER_BOX)
  await addProductsToBoxViaModal(page, requestId, detail.boxes[1].id, locBarcode, productId, QTY_PER_BOX)

  await expect(page.getByTestId('ff-mp-open-box-lines')).toBeVisible()
  await expectMpBoxDestructiveControlsHidden(
    page,
    detail.boxes.map((box) => box.id),
  )
  await expect(page.getByTestId(`ff-mp-box-print-${detail.boxes[0].id}`)).toBeEnabled()
  await expect(page.getByTestId('ff-mp-shipment-summary-distributed')).toHaveText(String(PLAN_QTY))
  await expect(page.getByTestId('ff-mp-shipment-summary-remaining')).toHaveText('0')
  await expect(page.getByTestId('ff-mp-next-step')).toHaveCount(0)
  await expect(page.getByTestId(/^ff-packaging-manual-qty-/)).toHaveCount(0)
  await expect(page.getByTestId('ff-packaging-pack-btn')).toHaveCount(0)
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/complete') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-complete').click(),
  ])
  await expect(page.getByTestId('ff-mp-shipment-summary-packed')).toHaveText(`${PLAN_QTY}/${PLAN_QTY}`)

  await expect(page.getByTestId('ff-mp-tab-final')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-ship')).toBeEnabled()
  await Promise.all([
    waitForPostOk(page, `/api/operations/marketplace-unload-requests/${requestId}/ship`),
    page.getByTestId('ff-mp-ship').click(),
  ])
  await expect(page.getByTestId('ff-supplies-doc-dialog')).toContainText('Отгружено')

  // TC-NEW-F15-SHIPPED-NO-BOX-MUTATIONS — shipped MP/FBO document keeps box print actions but hides mutating box/line controls.
  await expect(page.getByTestId('ff-mp-print-shipment-sheet')).toHaveCount(0)
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expect(page.getByTestId('ff-mp-boxes')).toBeVisible()
  await expectMpBoxOperationalControlsHidden(page)
  await expectMpBoxDestructiveControlsHidden(
    page,
    detail.boxes.map((box) => box.id),
  )
  await expect(page.getByTestId(`ff-mp-box-print-${detail.boxes[0].id}`)).toBeEnabled()
})
