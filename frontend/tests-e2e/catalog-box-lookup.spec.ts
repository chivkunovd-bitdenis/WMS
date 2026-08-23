import { expect, test, type Locator, type Page } from '@playwright/test'

import { INBOUND_API, seedFfSellerInbound, type InboundBoxesSeed } from './inbound-boxes-helpers'

async function createReceivingRequest(
  page: Page,
  seed: InboundBoxesSeed,
): Promise<{ requestId: string; headers: { Authorization: string } }> {
  const headers = { Authorization: `Bearer ${seed.token}` }
  const created = await page.request.post(INBOUND_API, {
    headers,
    data: { warehouse_id: seed.warehouseId },
  })
  expect(created.ok()).toBeTruthy()
  const requestId = String(((await created.json()) as { id: string }).id)

  const planned = await page.request.patch(`${INBOUND_API}/${requestId}`, {
    headers,
    data: { planned_box_count: 1 },
  })
  expect(planned.ok()).toBeTruthy()

  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: seed.productId, expected_qty: 1 },
  })
  expect(line.ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })).ok()).toBeTruthy()
  expect(
    (await page.request.post(`${INBOUND_API}/${requestId}/begin-receiving`, { headers })).ok(),
  ).toBeTruthy()
  return { requestId, headers }
}

async function createBox(
  page: Page,
  requestId: string,
  headers: { Authorization: string },
): Promise<{ id: string; barcode: string }> {
  const response = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as { id: string; internal_barcode: string }
  return { id: payload.id, barcode: payload.internal_barcode }
}

async function scanCatalogPackage(page: Page, barcode: string): Promise<void> {
  const search = page.getByTestId('ff-catalog-inbound-packages-scan')
  if (!(await search.isVisible().catch(() => false))) {
    await page.getByTestId('ff-catalog-tab-packages').click()
  }
  await search.fill(barcode)
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        response.url().includes('/api/operations/inbound-packages/lookup') &&
        response.url().includes(encodeURIComponent(barcode)),
    ),
    search.press('Enter'),
  ])
}

function packageByBarcode(page: Page, barcode: string): Locator {
  return page
    .locator('[data-testid^="ff-catalog-inbound-package-"]:not([data-testid="ff-catalog-inbound-packages"])')
    .filter({ hasText: barcode })
}

// TC-NEW-CATALOG-BOX-001: the printed box barcode opens the matching current contents.
// TC-NEW-CATALOG-BOX-LOOKUP
test('scan opens the received box and shows its current contents', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  const seed = await seedFfSellerInbound(page, `catalog-package-${Date.now()}`)
  const { requestId, headers } = await createReceivingRequest(page, seed)
  const box = await createBox(page, requestId, headers)

  const opened = await page.request.post(`${INBOUND_API}/${requestId}/boxes/open`, {
    headers,
    data: { barcode: box.barcode },
  })
  expect(opened.ok()).toBeTruthy()
  const scanned = await page.request.post(`${INBOUND_API}/${requestId}/boxes/${box.id}/scan`, {
    headers,
    data: { barcode: seed.sku },
  })
  expect(scanned.ok()).toBeTruthy()

  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-products-list')).toContainText(seed.sku)
  await expect(page.getByTestId('ff-catalog-tab-products')).toHaveAttribute('aria-selected', 'true')
  await page.getByTestId('ff-catalog-tab-packages').click()
  await expect(page.getByTestId('ff-catalog-products-panel')).toBeHidden()
  await expect(page.getByTestId('ff-catalog-inbound-packages-scanner')).toBeVisible()

  const freshName = 'Updated Box Product'
  const freshVendorArticle = `updated-${seed.vendorArticle}`
  const freshBarcode = `updated-${seed.barcode}`
  const freshSize = '48'
  const freshSellerName = 'Updated Box Seller'
  await page.route(/\/api\/operations\/inbound-packages\/lookup/, async (route) => {
    const response = await route.fetch()
    if (!response.ok()) {
      await route.fulfill({ response })
      return
    }
    const payload = (await response.json()) as {
      lines: Array<{
        name: string
        wb_vendor_code: string | null
        wb_barcode: string | null
        wb_size: string | null
        seller_name: string | null
      }>
    }
    for (const line of payload.lines) {
      line.name = freshName
      line.wb_vendor_code = freshVendorArticle
      line.wb_barcode = freshBarcode
      line.wb_size = freshSize
      line.seller_name = freshSellerName
    }
    await route.fulfill({ response, json: payload })
  })

  const lookupStartedAt = Date.now()
  await scanCatalogPackage(page, box.barcode)
  const packageItem = packageByBarcode(page, box.barcode)
  await expect(packageItem).toBeVisible()
  expect(Date.now() - lookupStartedAt).toBeLessThan(1_500)
  await expect(packageItem).toContainText('Короб № 1')
  await expect(packageItem).toContainText(seed.sku)
  const composition = packageItem.locator('[data-testid^="ff-catalog-inbound-composition-"]')
  await expect(composition.locator('thead')).toContainText('Название')
  await expect(composition.locator('thead')).toContainText('Артикул продавца')
  await expect(composition.locator('thead')).toContainText('SKU')
  await expect(composition.locator('thead')).toContainText('ШК')
  await expect(composition.locator('thead')).toContainText('Размер')
  await expect(composition.locator('thead')).toContainText('Селлер')
  await expect(composition.locator('thead')).toContainText('Документ прихода')
  const productRow = composition.locator('tbody tr').filter({ hasText: seed.sku })
  await expect(productRow).toContainText(freshName)
  await expect(productRow).toContainText(freshVendorArticle)
  await expect(productRow).toContainText(freshBarcode)
  await expect(productRow).toContainText(freshSize)
  await expect(productRow).toContainText(freshSellerName)
  await expect(productRow).toContainText('Приёмка №000001')
  await expect(productRow).toContainText(/\d{2}\.\d{2}\.\d{4}/)
  await expect(productRow).toContainText('1')

  const evidencePath = process.env.CATALOG_BOX_EVIDENCE_PATH
  if (evidencePath) {
    await packageItem.scrollIntoViewIfNeeded()
    await page.screenshot({ path: evidencePath })
  }

  await scanCatalogPackage(page, 'INB-UNKNOWN-CATALOG')
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toHaveText(
    'Короб или грузоместо не найдено',
  )
  await expect(packageItem).toBeVisible()
  await expect(composition).toBeVisible()

  await page.getByTestId('ff-catalog-tab-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-products-list')).toContainText(seed.sku)
})

// TC-NEW-CATALOG-BOX-002: one lookup owns the scanner until its fast read-only response returns.
test('scanner shows lookup progress and accepts the next box after completion', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `catalog-race-${Date.now()}`)
  const { requestId, headers } = await createReceivingRequest(page, seed)
  const firstBox = await createBox(page, requestId, headers)
  const secondBox = await createBox(page, requestId, headers)

  let releaseFirstLookup: (() => void) | undefined
  const firstLookupReleased = new Promise<void>((resolve) => {
    releaseFirstLookup = resolve
  })
  let markFirstLookupStarted: (() => void) | undefined
  const firstLookupStarted = new Promise<void>((resolve) => {
    markFirstLookupStarted = resolve
  })
  await page.route(/\/api\/operations\/inbound-packages\/lookup/, async (route) => {
    if (route.request().url().includes(encodeURIComponent(firstBox.barcode))) {
      markFirstLookupStarted?.()
      await firstLookupReleased
      await route.abort('failed')
      return
    }
    await route.continue()
  })

  await page.goto('/app/ff/products')
  await page.getByTestId('ff-catalog-tab-packages').click()
  const search = page.getByTestId('ff-catalog-inbound-packages-scan')
  await search.fill(firstBox.barcode)
  const firstScan = search.press('Enter')
  await firstLookupStarted

  await expect(search).toBeDisabled()
  await expect(page.getByText('Ищем короб…')).toBeVisible()

  const firstLookupFailed = page.waitForEvent(
    'requestfailed',
    (request) =>
      request.method() === 'GET' &&
      request.url().includes('/api/operations/inbound-packages/lookup') &&
      request.url().includes(encodeURIComponent(firstBox.barcode)),
  )
  releaseFirstLookup?.()
  await firstLookupFailed
  await firstScan

  await expect(search).toBeEnabled()
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toHaveText(
    'Нет связи с сервером. Повторите сканирование.',
  )
  await scanCatalogPackage(page, secondBox.barcode)
  await expect(packageByBarcode(page, secondBox.barcode)).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toBeHidden()
  await expect(search).toHaveValue(secondBox.barcode)
})
