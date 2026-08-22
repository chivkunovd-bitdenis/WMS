import { expect, test, type Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import {beginInboundReceivingWithBoxes,  fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'
import { seedHonestSignProductFirstInventory, selectHonestSignSeller } from './ff-honest-sign-helpers'

async function openCatalogArtifactTapeDialog(page: Page) {
  const suffix = Date.now()
  const email = `e2e-bg-tape-${suffix}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Background Tape')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [registration] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await registration.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const sellerResponse = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Background Tape Seller' }),
  })
  const sellerId = String(((await sellerResponse.json()) as { id: string }).id)
  const { productX } = await seedHonestSignProductFirstInventory(
    page,
    e2eApi,
    auth,
    { Authorization: `Bearer ${token}` },
    sellerId,
    `BG-TAPE-${suffix}`,
  )
  await page.request.patch(`${e2eApi}/products/${productX.id}/packaging-instructions`, {
    headers: auth,
    data: JSON.stringify({ requires_honest_sign: true, packaging_instructions: 'ЧЗ' }),
  })

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  const printAction = page.getByTestId(`ff-honest-sign-product-print-${productX.id}`)
  await printAction.click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  return { printAction }
}

// S-03-TC-008 — ожидание подготовки и только явное открытие готового PDF.
// S-03-TC-009 — повторное открытие тех же данных показывает существующее активное задание.
test('S-03 marking tape keeps one background job across dialog reopen and opens PDF explicitly', async ({ page }) => {
  test.setTimeout(180_000)
  const { printAction } = await openCatalogArtifactTapeDialog(page)
  let tapeStarts = 0
  let contentRequests = 0
  let releaseJob = false

  await page.route('**/operations/marking-codes/products/*/print', async (route) => {
    const request = route.request()
    const body = request.postDataJSON() as { layout_json: unknown }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        codes: ['010460000000000121BACKGROUND0001'],
        duplicate_copies: 1,
        quantity: 1,
        shortage: 0,
        layout: body.layout_json,
        printed_codes: [{
          id: 'code-background-1',
          cis_code: '010460000000000121BACKGROUND0001',
          has_label_artifact: true,
        }],
      }),
    })
  })
  await page.route('**/operations/marking-codes/label-artifact-tape', async (route) => {
    tapeStarts += 1
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: 'job-background-1' }),
    })
  })
  await page.route('**/operations/background-jobs/job-background-1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(releaseJob
        ? { status: 'done', result_json: { asset_id: 'asset-background-1' } }
        : { status: 'running', result_json: null }),
    })
  })
  await page.route('**/operations/fbs-print-assets/asset-background-1/content', async (route) => {
    contentRequests += 1
    await route.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4\n%%EOF' })
  })

  await page.getByTestId('marking-print-confirm').click()
  await expect(page.getByTestId('marking-print-preparing')).toContainText('Готовим ленту…')
  await expect(page.getByTestId('marking-print-preparing')).toContainText('Готовим к печати')
  await expect(page.getByTestId('marking-print-preparing')).toContainText('лента собирается в фоне')
  await expect(page.getByTestId('marking-print-confirm')).toHaveCount(0)
  expect(contentRequests).toBe(0)

  await page.getByTestId('marking-print-close-preparing').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden()
  await printAction.click()
  await expect(page.getByTestId('marking-print-preparing')).toBeVisible()
  expect(tapeStarts).toBe(1)

  releaseJob = true
  await expect(page.getByTestId('marking-print-ready')).toContainText('Готово')
  await expect(page.getByTestId('marking-print-open-ready')).toBeVisible()
  expect(contentRequests).toBe(0)

  const [popup] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByTestId('marking-print-open-ready').click(),
  ])
  await expect.poll(() => contentRequests).toBe(1)
  expect(popup).toBeTruthy()
  expect(tapeStarts).toBe(1)
})

// TC-NEW-002 — ЧЗ T1.3: конструктор печати — баннер нехватки, пресет «Парами», частичная печать.
// TC-NEW-CZ-PRINT-01 — ЧЗ этикетка 58×40: DataMatrix слева + служебный блок справа.
test('FF packaging: marking print constructor shortage and pairs preview', async ({ page }) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    window.__WMS_CAPTURE_PRINT_HTML__ = true
    window.print = () => {}
  })
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
  const { boxes: inboundBoxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, { boxCount: 1 })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, inboundBoxes, sku, [3])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })

  await page.goto('/app/ff/packaging')
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Short' }).click()
  await page.getByTestId('ff-packaging-create-location').click()
  await page.getByRole('option', { name: 'Сортировка' }).click()
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible()
  await page.locator('[data-testid^="ff-packaging-create-row-select-"]').first().click()
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
  await expect(page.getByTestId('marking-print-cz-qty')).toBeVisible()
  await expect(page.getByTestId('marking-print-wb-qty')).toBeVisible()
  await expect(page.getByTestId('marking-print-tape-item-0')).toHaveText('ЧЗ')
  await expect(page.getByTestId('marking-print-tape-item-1')).toHaveText('ЧЗ')
  await expect(page.getByTestId('marking-print-preview-unit-1')).toBeVisible()
  await expect(page.getByTestId('marking-print-preview-chip-1-0')).toHaveText('ЧЗ')
  await expect(page.getByTestId('marking-print-preview-chip-1-1')).toHaveText('ЧЗ')

  await page.getByTestId('marking-print-wb-qty').locator('input').fill('3')
  await expect(page.getByTestId('marking-print-tape-item-2')).toHaveText('ШК ВБ')
  await expect(page.getByTestId('marking-print-tape-item-4')).toHaveText('ШК ВБ')
  await page.getByTestId('marking-print-tape-item-4').dragTo(page.getByTestId('marking-print-tape-item-0'))
  await expect(page.getByTestId('marking-print-tape-item-0')).toHaveText('ШК ВБ')
  await expect(page.getByTestId('marking-print-preview-chip-1-0')).toHaveText('ШК ВБ')

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

  await page.waitForFunction(() => Boolean(window.__WMS_LAST_PRINT_HTML__))
  const printHtml = await page.evaluate(() => window.__WMS_LAST_PRINT_HTML__ ?? '')
  expect(printHtml).toContain('label--cz')
  expect(printHtml).toContain('cz-label-info')
  expect(printHtml).toContain('data-tape-block="cz"')
  expect(printHtml).toContain('data-tape-block="label"')
  expect(printHtml).toContain('cz-matrix')
  expect(printHtml).not.toContain('class="tail"')

  await expect(page.getByText('напечатано 2 / нужно 3')).toBeVisible()
  await expect(page.getByText(/в пуле\s+\d+/)).toBeVisible()
})
