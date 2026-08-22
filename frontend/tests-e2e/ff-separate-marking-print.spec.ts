import { expect, test, type Page } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { beginInboundReceivingWithBoxes, fulfillInboundViaBoxScans } from './inbound-boxes-helpers'
import { openFulfillmentRegistration } from './auth-flow'
import { seedHonestSignProductFirstInventory, selectHonestSignSeller } from './ff-honest-sign-helpers'

async function openRetryableArtifactTapeDialog(page: Page) {
  const suffix = Date.now()
  const email = `e2e-bg-retry-${suffix}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Retryable Tape')
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
    data: JSON.stringify({ name: 'E2E Retryable Tape Seller' }),
  })
  const sellerId = String(((await sellerResponse.json()) as { id: string }).id)
  const { productX } = await seedHonestSignProductFirstInventory(
    page,
    e2eApi,
    auth,
    { Authorization: `Bearer ${token}` },
    sellerId,
    `BG-RETRY-${suffix}`,
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

// S-03-TC-014 — ошибка подготовки не показывает технические детали и даёт безопасный повтор.
// S-03-TC-015 — истёкший PDF не открывается и требует осознанной новой подготовки.
test('S-03 marking tape retries safely after failure and expired asset', async ({ page }) => {
  test.setTimeout(180_000)
  const { printAction } = await openRetryableArtifactTapeDialog(page)
  let tapeStarts = 0
  let assetRequests = 0

  await page.route('**/operations/marking-codes/products/*/print', async (route) => {
    const body = route.request().postDataJSON() as { layout_json: unknown }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        codes: ['010460000000000121RETRYBACKGROUND01'],
        duplicate_copies: 1,
        quantity: 1,
        shortage: 0,
        layout: body.layout_json,
        printed_codes: [{
          id: 'code-retry-background-1',
          cis_code: '010460000000000121RETRYBACKGROUND01',
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
      body: JSON.stringify({ job_id: `job-retry-${tapeStarts}` }),
    })
  })
  await page.route('**/operations/background-jobs/job-retry-*', async (route) => {
    const jobId = route.request().url().split('/').pop()
    const payload = jobId === 'job-retry-1'
      ? { status: 'failed', result_json: null }
      : jobId === 'job-retry-2'
        ? { status: 'done', result_json: { asset_id: 'asset-expired-1' } }
        : { status: 'running', result_json: null }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })
  await page.route('**/operations/fbs-print-assets/asset-expired-1/content', async (route) => {
    assetRequests += 1
    await route.fulfill({ status: 410, contentType: 'application/json', body: JSON.stringify({ detail: 'expired' }) })
  })

  await page.getByTestId('marking-print-confirm').click()
  const preparationError = page.getByTestId('marking-print-preparation-error')
  await expect(preparationError).toContainText('Не удалось собрать ленту. Попробуйте ещё раз')
  await expect(preparationError).toContainText('Повторить')
  await expect(preparationError).toContainText('Закрыть')
  await expect(preparationError).not.toContainText('job-retry-1')
  await expect(preparationError).not.toContainText('background-jobs')

  await page.getByTestId('marking-print-retry').click()
  await expect(page.getByTestId('marking-print-preparing')).toBeVisible()
  await expect(page.getByTestId('marking-print-ready')).toBeVisible()
  expect(tapeStarts).toBe(2)
  expect(assetRequests).toBe(0)

  await page.keyboard.press('Escape')
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden()
  await printAction.click()
  await expect(page.getByTestId('marking-print-ready')).toBeVisible()
  expect(tapeStarts).toBe(2)

  await page.getByTestId('marking-print-open-ready').click()
  await expect(page.getByTestId('marking-print-preparation-error')).toContainText(
    'Срок хранения ленты истёк. Соберите её ещё раз',
  )
  expect(assetRequests).toBe(1)
  await page.getByTestId('marking-print-retry').click()
  await expect(page.getByTestId('marking-print-preparing')).toBeVisible()
  expect(tapeStarts).toBe(3)
})

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

  await page.goto('/app/ff/packaging')
  await page.getByTestId('ff-packaging-create-open').click()
  await page.getByTestId('ff-packaging-create-warehouse').click()
  await page.getByRole('option', { name: 'WH Sep' }).click()
  await page.getByTestId('ff-packaging-create-location').click()
  await page.getByRole('option', { name: 'Сортировка' }).click()
  await expect(page.getByTestId('ff-packaging-create-row')).toBeVisible()
  await page.locator('[data-testid^="ff-packaging-create-row-select-"]').first().click()
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

  const linePrintBtn = page.locator('[data-testid^="ff-packaging-line-print-"]').first()
  await expect(linePrintBtn).toBeVisible()

  await page.evaluate(() => {
    localStorage.setItem('wms.print.labelSizeId', '70x120')
    localStorage.removeItem('wms.print.labelSizeId.cz')
    localStorage.removeItem('wms.print.labelSizeId.label')
    ;(window as unknown as { __WMS_CAPTURE_PRINT_HTML__?: boolean }).__WMS_CAPTURE_PRINT_HTML__ = true
  })
  const separatePrintWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/packaging-lines/') &&
      r.url().endsWith('/print') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await linePrintBtn.click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await expect(page.getByTestId('marking-print-separate-cz')).toBeVisible()
  await expect(page.getByTestId('marking-print-separate-wb')).toBeVisible()
  await expect(page.getByTestId('marking-print-sep-cz-print')).toBeVisible()
  await expect(page.getByTestId('marking-print-sep-wb-print')).toBeVisible()
  await expect(page.getByTestId('marking-print-confirm')).toHaveCount(0)
  await expect(page.getByTestId('marking-print-separate-close')).toBeVisible()
  await expect(page.getByTestId('marking-print-cz-label-size')).toContainText('58 × 40')
  await expect(page.getByTestId('marking-print-wb-label-size')).toContainText('58 × 40')

  await Promise.all([separatePrintWait, page.getByTestId('marking-print-sep-cz-print').click()])
  await expect(page.getByTestId('marking-print-sep-cz-print')).toContainText('ЧЗ напечатаны ✓')
  await expect(page.getByTestId('marking-print-separate-wb')).toBeVisible()
  const printedHtml = await page.evaluate(
    () => (window as unknown as { __WMS_LAST_PRINT_HTML__?: string }).__WMS_LAST_PRINT_HTML__ ?? '',
  )
  expect(printedHtml).toContain('size: 58mm 40mm')

  await page.getByTestId('marking-print-separate-close').click()
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden()
  await expect(page.locator('[data-testid^="ff-packaging-line-menu-btn-"]').first()).toBeVisible()

  await linePrintBtn.click()
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible()
  await expect(page.getByTestId('marking-print-separate-wb')).toBeVisible()
  await expect(page.getByTestId('marking-print-sep-cz-print')).toBeVisible()

  await page.getByTestId('marking-print-sep-cz-print').click()
  await expect(page.getByTestId('marking-print-reprint-notice')).toBeVisible()
  await expect(page.getByTestId('marking-reprint-pick-list')).toBeVisible()
})
