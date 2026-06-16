import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-001 — ЧЗ: импорт кодов и печать пачкой из строки задания на упаковку.
test('FF packaging: print honest sign codes for line quantity', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-cz-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-CZ-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E CZ')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
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
    data: JSON.stringify({ name: 'E2E CZ Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH CZ', code: `wh-cz-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Брюки ЧЗ',
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
    data: JSON.stringify({ requires_honest_sign: true, packaging_instructions: 'ЧЗ x2' }),
  })

  const cis = `01${'0'.repeat(10)}123421${'A'.repeat(20)}0001`
  const csv = `cis,sku_code\n${cis},${sku}`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      seller_id: sellerId,
      file: {
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

  await page.getByTestId('nav-ff-honest-sign').click()
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible()
  await page.getByTestId(`ff-honest-sign-seller-${sellerId}`).click()
  await expect(page.getByTestId(`ff-honest-sign-row-${productId}`)).toBeVisible()

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH CZ' }).click()
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
  await expect(page.getByTestId('ff-packaging-print-marking')).toBeVisible()

  const printWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/packaging-lines/') &&
      r.url().endsWith('/print') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await page.getByTestId('ff-packaging-print-marking').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await Promise.all([printWait, page.getByTestId('marking-print-confirm').click()])

  const printBody = (await (await printWait).json()) as { quantity: number; codes: string[] }
  expect(printBody.quantity).toBe(1)
  expect(printBody.codes).toHaveLength(1)

  await expect(page.getByText('напеч. 1')).toBeVisible()
})
