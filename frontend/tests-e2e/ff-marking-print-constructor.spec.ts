import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-002 — ЧЗ T1.3: конструктор печати — баннер нехватки, пресет «Парами», частичная печать.
test('FF packaging: marking print constructor shortage and pairs preview', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-cz-short-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-CZ-S-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E CZ Short')
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
    data: JSON.stringify({ name: 'E2E Short Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Short', code: `wh-s-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Куртка ЧЗ',
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
    data: JSON.stringify({ requires_honest_sign: true }),
  })

  const gtin = '000000009999'
  const cisLines = [0, 1].map((i) => `01${gtin}21${'B'.repeat(20)}${String(i).padStart(4, '0')}`)
  const csv = `cis,sku_code\n${cisLines.map((c) => `${c},${sku}`).join('\n')}`
  await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Short pool', product_ids: [productId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv),
      },
    },
  })

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: JSON.stringify({ product_id: productId, expected_qty: 3 }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  const primIn = await page.request.post(`${baseIn}/${inboundId}/primary-accept`, {
    headers: auth,
    data: { actual_box_count: 1 },
  })
  const primInBody = (await primIn.json()) as {
    boxes: { id: string; internal_barcode: string }[]
  }
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, primInBody.boxes, sku, [3])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Short' }).click()
  await page.getByTestId(`ff-packaging-create-qty-${productId}`).fill('3')
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

  await expect(page.getByTestId('ff-packaging-print-marking')).toBeVisible()
  await page.getByTestId('ff-packaging-print-marking').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await expect(page.getByTestId('marking-print-shortage-banner')).toContainText('Не хватает 1')
  await expect(page.getByTestId('marking-print-preset-pairs')).toBeChecked()
  await expect(page.getByTestId('marking-print-preview-unit-1')).toBeVisible()
  await expect(page.getByTestId('marking-print-preview-chip-1-0')).toHaveText('ЧЗ')
  await expect(page.getByTestId('marking-print-preview-chip-1-1')).toHaveText('ЧЗ')

  await page.getByTestId('marking-print-preset-label_cz').check()
  await expect(page.getByTestId('marking-print-preview-tape-count')).toContainText('6 этикеток на 3 ед.')
  await expect(page.getByTestId('marking-print-preview-chip-1-0')).toHaveText('ШК ВБ')
  await expect(page.getByTestId('marking-print-preview-chip-1-1')).toHaveText('ЧЗ')

  await page.getByTestId('marking-print-allow-partial').check()
  const printWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/packaging-lines/') &&
      r.url().endsWith('/print') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await Promise.all([printWait, page.getByTestId('marking-print-confirm').click()])

  const printBody = (await (await printWait).json()) as { quantity: number; shortage: number | null }
  expect(printBody.quantity).toBe(2)
  expect(printBody.shortage).toBe(1)

  await expect(page.getByText('напечатано 2 / нужно 2')).toBeVisible()
  await expect(page.getByText(/дост\.\s+\d+\s+в пуле/)).toBeVisible()
})
