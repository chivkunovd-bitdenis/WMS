import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { beginInboundReceivingWithBoxes, fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-SEP-PRINT-01 — раздельная печать: две секции ЧЗ и ШК ВБ в модалке.
test('FF settings: separate marking print shows split print sections', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-sep-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-SEP-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Sep Print')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const settingsPatch = await page.request.patch(`${e2eApi}/tenant/settings`, {
    headers: auth,
    data: JSON.stringify({ separate_marking_print_enabled: true }),
  })
  expect(settingsPatch.ok()).toBeTruthy()
  await page.reload()
  await expect(page.getByTestId('nav-ff-packaging')).toBeVisible()

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Sep Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Sep', code: `wh-sep-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Sep Product',
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

  const gtin = '000000001234'
  const cisRows = Array.from({ length: 3 }, (_, i) => {
    const cis = `01${gtin}21${'B'.repeat(19)}${String(i).padStart(4, '0')}`
    return `${cis},${sku}`
  })
  const csv = `cis,sku_code\n${cisRows.join('\n')}`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E Sep Pool', product_ids: [productId] }]),
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
    data: JSON.stringify({ product_id: productId, expected_qty: 2 }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  const { boxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, { boxCount: 1 })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, boxes, sku, [2])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Sep' }).click()
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
  await expect(page.getByTestId('marking-print-separate-cz')).toBeVisible()
  await expect(page.getByTestId('marking-print-separate-wb')).toBeVisible()
  await expect(page.getByTestId('marking-print-sep-cz-print')).toBeVisible()
  await expect(page.getByTestId('marking-print-sep-wb-print')).toBeVisible()
  await expect(page.getByTestId('marking-print-confirm')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-separate-close')).toBeVisible()
})
