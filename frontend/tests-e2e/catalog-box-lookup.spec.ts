import { expect, test, type Locator, type Page } from '@playwright/test'

import { INBOUND_API, seedFfSellerInbound, type InboundBoxesSeed } from './inbound-boxes-helpers'

async function createReceivingRequest(
  page: Page,
  seed: InboundBoxesSeed,
  options: { productIds?: string[]; plannedBoxCount?: number; expectedQty?: number } = {},
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
    data: { planned_box_count: options.plannedBoxCount ?? 1 },
  })
  expect(planned.ok()).toBeTruthy()

  for (const productId of options.productIds ?? [seed.productId]) {
    const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
      headers,
      data: { product_id: productId, expected_qty: options.expectedQty ?? 1 },
    })
    expect(line.ok()).toBeTruthy()
  }
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

async function createSecondSellerProduct(
  page: Page,
  seed: InboundBoxesSeed,
): Promise<{ productId: string; sku: string; barcode: string; sellerName: string }> {
  const headers = { Authorization: `Bearer ${seed.token}` }
  const sellerName = `Second filter seller ${seed.suffix}`
  const seller = await page.request.post('/api/sellers', { headers, data: { name: sellerName } })
  expect(seller.ok()).toBeTruthy()
  const sellerId = String(((await seller.json()) as { id: string }).id)
  const sku = `second-filter-sku-${seed.suffix}`
  const barcode = `second-filter-barcode-${seed.suffix}`
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name: `Second filter product ${seed.suffix}`,
      sku_code: sku,
      wb_vendor_code: `second-filter-article-${seed.suffix}`,
      wb_barcode: barcode,
      wb_size: '42',
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
      seller_id: sellerId,
    },
  })
  expect(product.ok()).toBeTruthy()
  return { productId: String(((await product.json()) as { id: string }).id), sku, barcode, sellerName }
}

async function createSameSellerProduct(
  page: Page,
  seed: InboundBoxesSeed,
): Promise<{ productId: string; sku: string }> {
  const headers = { Authorization: `Bearer ${seed.token}` }
  const sku = `same-seller-filter-sku-${seed.suffix}`
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name: `Other first seller product ${seed.suffix}`,
      sku_code: sku,
      wb_vendor_code: `same-seller-filter-article-${seed.suffix}`,
      wb_barcode: `same-seller-filter-barcode-${seed.suffix}`,
      wb_size: '42',
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
      seller_id: seed.sellerId,
    },
  })
  expect(product.ok()).toBeTruthy()
  return { productId: String(((await product.json()) as { id: string }).id), sku }
}

function packageHeader(page: Page, packageId: string): Locator {
  return page.locator(`#ff-catalog-inbound-package-header-${packageId}`)
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
  const { requestId, headers } = await createReceivingRequest(page, seed, { expectedQty: 2 })
  const firstBox = await createBox(page, requestId, headers)
  const secondBox = await createBox(page, requestId, headers)
  for (const box of [firstBox, secondBox]) {
    expect(
      (
        await page.request.post(`${INBOUND_API}/${requestId}/boxes/open`, {
          headers,
          data: { barcode: box.barcode },
        })
      ).ok(),
    ).toBeTruthy()
    expect(
      (
        await page.request.post(`${INBOUND_API}/${requestId}/boxes/${box.id}/scan`, {
          headers,
          data: { barcode: seed.sku },
        })
      ).ok(),
    ).toBeTruthy()
  }

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

// TC-CATALOG-BOX-FILTER-001: filters stay inside the boxes tab, apply as AND to composition rows,
// hide empty packages, and do not make independent accordions mutually exclusive.
test('filters boxes by seller and product, hides empty boxes, and keeps multiple boxes open', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  const seed = await seedFfSellerInbound(page, `catalog-filters-${Date.now()}`)
  const sameSellerProduct = await createSameSellerProduct(page, seed)
  const secondProduct = await createSecondSellerProduct(page, seed)

  const mixedRequest = await createReceivingRequest(page, seed, {
    productIds: [seed.productId, sameSellerProduct.productId],
    plannedBoxCount: 2,
  })
  const mixedBox = await createBox(page, mixedRequest.requestId, mixedRequest.headers)
  const emptyBox = await createBox(page, mixedRequest.requestId, mixedRequest.headers)
  expect(
    (
      await page.request.post(`${INBOUND_API}/${mixedRequest.requestId}/boxes/open`, {
        headers: mixedRequest.headers,
        data: { barcode: mixedBox.barcode },
      })
    ).ok(),
  ).toBeTruthy()
  expect(
    (
      await page.request.post(`${INBOUND_API}/${mixedRequest.requestId}/boxes/${mixedBox.id}/scan`, {
        headers: mixedRequest.headers,
        data: { barcode: seed.sku },
      })
    ).ok(),
  ).toBeTruthy()
  expect(
    (
      await page.request.post(`${INBOUND_API}/${mixedRequest.requestId}/boxes/${mixedBox.id}/scan`, {
        headers: mixedRequest.headers,
        data: { barcode: sameSellerProduct.sku },
      })
    ).ok(),
  ).toBeTruthy()

  const secondRequest = await createReceivingRequest(page, seed, { productIds: [secondProduct.productId] })
  const secondBox = await createBox(page, secondRequest.requestId, secondRequest.headers)
  expect(
    (
      await page.request.post(`${INBOUND_API}/${secondRequest.requestId}/boxes/open`, {
        headers: secondRequest.headers,
        data: { barcode: secondBox.barcode },
      })
    ).ok(),
  ).toBeTruthy()
  expect(
    (
      await page.request.post(`${INBOUND_API}/${secondRequest.requestId}/boxes/${secondBox.id}/scan`, {
        headers: secondRequest.headers,
        data: { barcode: secondProduct.sku },
      })
    ).ok(),
  ).toBeTruthy()

  await page.goto('/app/ff/products')
  await page.getByTestId('ff-catalog-tab-packages').click()
  const mixedPackage = page.getByTestId(`ff-catalog-inbound-package-${mixedBox.id}`)
  const secondPackage = page.getByTestId(`ff-catalog-inbound-package-${secondBox.id}`)
  await expect(mixedPackage).toBeVisible()
  await expect(secondPackage).toBeVisible()
  await expect(page.getByTestId(`ff-catalog-inbound-package-${emptyBox.id}`)).toHaveCount(0)

  await packageHeader(page, mixedBox.id).click()
  await expect(mixedPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeVisible()
  await packageHeader(page, secondBox.id).click()
  await expect(mixedPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeVisible()
  await expect(secondPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeVisible()

  await packageHeader(page, mixedBox.id).click()
  await expect(mixedPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeHidden()
  await page.getByTestId('ff-catalog-inbound-packages-expand-all').click()
  await expect(mixedPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeVisible()
  await expect(secondPackage.locator('[data-testid^="ff-catalog-inbound-composition-"]')).toBeVisible()

  const sellerFilter = page.getByTestId('ff-catalog-inbound-packages-seller-filter').getByRole('combobox')
  await sellerFilter.click()
  await page.getByRole('option', { name: `Box Seller ${seed.suffix}`, exact: true }).click()
  await expect(page.getByRole('listbox')).toBeHidden()
  const productSearch = page.getByTestId('ff-catalog-inbound-packages-product-search')
  await productSearch.fill('bOx PrOdUcT')
  await expect(mixedPackage).toBeVisible()
  await expect(secondPackage).toHaveCount(0)
  const mixedRows = mixedPackage.locator('[data-testid^="ff-catalog-inbound-composition-"] tbody tr')
  await expect(mixedRows).toHaveCount(1)
  await expect(mixedRows).toContainText(seed.sku)
  await expect(mixedRows).not.toContainText(secondProduct.sku)

  await productSearch.fill(seed.sku.toUpperCase())
  await expect(mixedPackage).toBeVisible()
  await expect(mixedRows).toHaveCount(1)
  await productSearch.fill('bOx PrOdUcT')

  const evidencePath = process.env.CATALOG_BOX_FILTERS_EVIDENCE_PATH
  if (evidencePath) {
    await page.waitForTimeout(250)
    await page.screenshot({ path: evidencePath, fullPage: true })
  }

  await productSearch.fill(secondProduct.barcode.toUpperCase())
  await expect(mixedPackage).toHaveCount(0)
  await expect(secondPackage).toHaveCount(0)

  await sellerFilter.click()
  await page.getByRole('option', { name: 'Все селлеры', exact: true }).click()
  await expect(page.getByRole('listbox')).toBeHidden()
  await expect(mixedPackage).toHaveCount(0)
  await expect(secondPackage).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-package-' + emptyBox.id)).toHaveCount(0)
  await page.getByTestId('ff-catalog-inbound-packages-expand-all').click()
  const searchFilteredSecondRows = secondPackage.locator('[data-testid^="ff-catalog-inbound-composition-"] tbody tr')
  await expect(searchFilteredSecondRows).toHaveCount(1)
  await expect(searchFilteredSecondRows).toContainText(secondProduct.sku)

  await productSearch.fill('')
  await expect(mixedPackage).toBeVisible()
  await expect(secondPackage).toBeVisible()
})
