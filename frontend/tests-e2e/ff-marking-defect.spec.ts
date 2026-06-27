import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-005 — брак напечатанного ЧЗ создаёт pending-запрос в очереди перепечатки.
test('FF packaging: defect button creates pending reprint request', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-defect-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-DEF-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Defect')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const bearer = { Authorization: `Bearer ${token}` }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Defect Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Defect', code: `wh-def-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Брюки брак',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  await page.request.patch(`${e2eApi}/products/${productId}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ requires_honest_sign: true, packaging_instructions: 'ЧЗ' }),
  })

  const gtin = '000000001234'
  const cis = `01${gtin}21${'D'.repeat(20)}0001`
  const cis2 = `01${gtin}21${'D'.repeat(20)}0002`
  const csv = `cis,sku_code\n${cis},${sku}\n${cis2},${sku}`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E Defect Pool', product_ids: [productId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 1 }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  const primIn = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primInBody = (await primIn.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, primInBody.boxes, sku, [1])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Defect' }).click()
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible()

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/packaging-tasks') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-create-submit').click(),
  ])

  await expect(page.getByTestId('ff-packaging-task-panel')).toBeVisible()
  await page.getByTestId('ff-packaging-print-marking').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marking-codes/packaging-lines/') &&
        r.url().endsWith('/print') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('marking-print-confirm').click(),
  ])

  const defectWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/codes/') &&
      r.url().endsWith('/defect') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await Promise.all([defectWait, page.getByTestId('ff-packaging-defect-marking').click()])
  const defectBody = (await (await defectWait).json()) as { status: string }
  expect(defectBody.status).toBe('pending')

  await page.getByTestId('nav-ff-honest-sign-reprints').click()
  await expect(page.getByTestId('ff-honest-sign-reprints-page-table')).toBeVisible()
  const row = page.locator('[data-testid^="ff-honest-sign-reprints-page-row-"]').first()
  await expect(row).toBeVisible()
  const requestId = (await row.getAttribute('data-testid'))?.replace(
    'ff-honest-sign-reprints-page-row-',
    '',
  )
  expect(requestId).toBeTruthy()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/reprint-requests/${requestId}/replace`) &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId(`ff-honest-sign-reprints-page-replace-${requestId}`).click(),
  ])
  await expect(page.getByTestId('ff-honest-sign-reprints-page-empty')).toBeVisible()
})
