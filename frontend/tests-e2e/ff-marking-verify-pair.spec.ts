import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-006 — проверка пары ЧЗ: одинаковые наклейки → зелёный, разные → красный.
test('FF packaging: verify-pair shows green on match and red on mismatch', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-pair-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-PAIR-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pair')
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
    data: JSON.stringify({ name: 'E2E Pair Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Pair', code: `wh-pair-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Pair Product',
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

  const gtin = '000000001234'
  const cis = `01${gtin}21${'V'.repeat(20)}0001`
  const csv = `cis,sku_code\n${cis},${sku}`
  await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E Pair Pool', product_ids: [productId] }]),
      files: { name: 'codes.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
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
  await page.getByRole('option', { name: 'WH Pair' }).click()
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

  await page.getByTestId('ff-packaging-print-marking').click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marking-codes/packaging-lines/') &&
        r.url().endsWith('/print'),
    ),
    page.getByTestId('marking-print-confirm').click(),
  ])

  await expect(page.getByTestId('marking-verify-pair-panel')).toBeVisible()
  const pairInput = page.getByTestId('marking-verify-pair-input')

  await pairInput.fill(cis)
  await pairInput.press('Enter')
  await expect(page.getByTestId('marking-verify-pair-step')).toContainText('вторую')

  const verifyWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/verify-pair') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await pairInput.fill(cis)
  await Promise.all([verifyWait, pairInput.press('Enter')])
  await expect(page.getByTestId('marking-verify-pair-ok')).toBeVisible()

  await pairInput.fill(cis)
  await pairInput.press('Enter')
  const mismatchWait = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().includes('/verify-pair'),
  )
  await pairInput.fill(`${cis}x`)
  await Promise.all([mismatchWait, pairInput.press('Enter')])
  await expect(page.getByTestId('marking-verify-pair-error')).toBeVisible()
})
