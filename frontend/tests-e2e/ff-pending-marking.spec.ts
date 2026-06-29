import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import {beginInboundReceivingWithBoxes,  fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-007 — ворклист pending-marking: строка есть до печати и исчезает после.
test('FF pending marking worklist row disappears after print', async ({ page }) => {
  test.setTimeout(120_000)
  const email = `e2e-pending-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-PND-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pending')
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
    data: JSON.stringify({ name: 'E2E Pending Seller', email: `s-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)
  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Pnd', code: `wh-pnd-${Date.now()}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)
  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Pending Product',
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
  const cis = `01${gtin}21${'W'.repeat(20)}0001`
  await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Pool', product_ids: [productId] }]),
      files: { name: 'codes.csv', mimeType: 'text/csv', buffer: Buffer.from(`cis\n${cis}`) },
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
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, { boxCount: 1 })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, sku, [1])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Pnd' }).click()
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

  // TC-NEW-011 — CROSS-02: бейдж на упаковке = число строк pending-marking.
  await page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      r.url().includes('/operations/marking-codes/pending-marking') &&
      r.status() === 200,
  )
  await expect(page.getByTestId('ff-packaging-pending-badge')).toContainText('1')

  await page.getByTestId('ff-packaging-pending-link').click()
  await expect(page.getByTestId('ff-pending-marking-page')).toBeVisible()
  await expect(page.getByTestId('ff-pending-marking-count')).toHaveText('1 строк')
  await expect(page.getByTestId('ff-pending-marking-row')).toHaveCount(1)

  await page.locator('button[data-testid^="ff-pending-marking-print-"]:not([data-testid="ff-pending-marking-print-selected"])').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/operations/marking-codes/packaging-lines/') &&
        r.url().endsWith('/print'),
    ),
    page.getByTestId('marking-print-confirm').click(),
  ])

  await expect(page.getByTestId('ff-pending-marking-empty')).toBeVisible()
})

// TC-NEW-008 — PENDING-01: чекбоксы и печать выбранных (каждая лента по своему товару).
test('FF pending marking bulk print selected rows', async ({ page }) => {
  test.setTimeout(180_000)
  const email = `e2e-pending-bulk-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const ts = Date.now()

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pending Bulk')
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
    data: JSON.stringify({ name: 'E2E Bulk Seller', email: `s-bulk-${ts}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)
  const whRes = await page.request.post(`${e2eApi}/warehouses`, {
    headers: auth,
    data: JSON.stringify({ name: 'WH Bulk', code: `wh-bulk-${ts}` }),
  })
  const whId = String(((await whRes.json()) as { id: string }).id)

  const productSpecs = [
    { name: 'E2E Bulk A', sku: `SKU-BA-${ts}`, gtin: '000000001111' },
    { name: 'E2E Bulk B', sku: `SKU-BB-${ts}`, gtin: '000000002222' },
  ] as const

  for (const spec of productSpecs) {
    const prRes = await page.request.post(`${e2eApi}/products`, {
      headers: auth,
      data: JSON.stringify({
        name: spec.name,
        sku_code: spec.sku,
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
    const cis = `01${spec.gtin}21${'X'.repeat(20)}0001`
    await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
      headers: bearer,
      multipart: {
        seller_id: sellerId,
        pools_json: JSON.stringify([{ title: `Pool ${spec.sku}`, product_ids: [productId] }]),
        files: { name: 'codes.csv', mimeType: 'text/csv', buffer: Buffer.from(`cis\n${cis}`) },
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
    const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, { boxCount: 1 })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, spec.sku, [1])
    await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
    await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })
  }

  await page.getByTestId('nav-ff-packaging').click()
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Bulk' }).click()
  await expect(page.getByTestId('ff-packaging-create-row')).toHaveCount(2)
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

  // TC-NEW-011 — CROSS-02: бейдж = число строк в списке pending-marking.
  await page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      r.url().includes('/operations/marking-codes/pending-marking') &&
      r.status() === 200,
  )
  await expect(page.getByTestId('ff-packaging-pending-badge')).toContainText('2')

  await page.getByTestId('ff-packaging-pending-link').click()
  await expect(page.getByTestId('ff-pending-marking-page')).toBeVisible()
  await expect(page.getByTestId('ff-pending-marking-count')).toHaveText('2 строк')
  await expect(page.getByTestId('ff-pending-marking-row')).toHaveCount(2)

  await page.getByTestId('ff-pending-marking-select-all').click()
  await expect(page.getByTestId('ff-pending-marking-print-selected')).toBeEnabled()
  await expect(page.getByTestId('ff-pending-marking-print-selected')).toContainText('(2)')

  await page.getByTestId('ff-pending-marking-print-selected').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()

  const printedLineIds: string[] = []
  for (let printed = 0; printed < 2; printed += 1) {
    await expect(page.getByTestId('marking-print-header')).toBeVisible()
    const [printRes] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.request().method() === 'POST' &&
          r.url().includes('/operations/marking-codes/packaging-lines/') &&
          r.url().endsWith('/print'),
      ),
      page.getByTestId('marking-print-confirm').click(),
    ])
    const lineId = printRes.url().split('/packaging-lines/')[1]?.split('/')[0] ?? ''
    printedLineIds.push(lineId)
    if (printed < 1) {
      await expect(page.getByTestId('marking-print-dialog')).toBeVisible({ timeout: 15_000 })
    }
  }

  expect(new Set(printedLineIds).size).toBe(2)

  await expect(page.getByTestId('marking-print-dialog')).toBeHidden()
  await expect(page.getByTestId('ff-pending-marking-empty')).toBeVisible()
})
