import { expect, test, type Locator, type Page } from '@playwright/test'

import { waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { INBOUND_API, seedFfSellerInbound } from './inbound-boxes-helpers'

type StaffPermissions = {
  settings: boolean
  mp_shipments: boolean
  reception: boolean
  cells: boolean
  inventory: boolean
  packaging: boolean
  shift_lead: boolean
}

const NO_PERMISSIONS: StaffPermissions = {
  settings: false,
  mp_shipments: false,
  reception: false,
  cells: false,
  inventory: false,
  packaging: false,
  shift_lead: false,
}

async function scanCatalogPackage(page: Page, barcode: string): Promise<void> {
  const search = page.getByTestId('ff-catalog-search')
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

function catalogPackageByBarcode(page: Page, barcode: string): Locator {
  return page
    .locator('[data-testid^="ff-catalog-inbound-package-"]:not([data-testid="ff-catalog-inbound-packages"])')
    .filter({ hasText: barcode })
}

function packageQtyCell(packageItem: Locator, sku: string): Locator {
  return packageItem
    .locator('[data-testid^="ff-catalog-inbound-composition-"] tbody tr')
    .filter({ hasText: sku })
    .locator('td')
    .nth(3)
}

async function createOtherSellerBox(
  page: Page,
  seed: { token: string; warehouseId: string; suffix: string },
): Promise<{ barcode: string; sku: string; name: string; productBarcode: string }> {
  const headers = { Authorization: `Bearer ${seed.token}` }
  const seller = await page.request.post('/api/sellers', {
    headers,
    data: { name: `Box Seller B ${seed.suffix}` },
  })
  expect(seller.ok()).toBeTruthy()
  const sellerId = String(((await seller.json()) as { id: string }).id)
  const sku = `sku-box-b-${seed.suffix}`
  const name = `Box Product B ${seed.suffix}`
  const productBarcode = `B-CATALOG-${seed.suffix}`
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name,
      sku_code: sku,
      wb_barcode: productBarcode,
      seller_id: sellerId,
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
    },
  })
  expect(product.ok()).toBeTruthy()
  const productId = String(((await product.json()) as { id: string }).id)
  const inbound = await page.request.post(INBOUND_API, { headers, data: { warehouse_id: seed.warehouseId } })
  expect(inbound.ok()).toBeTruthy()
  const requestId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: productId, expected_qty: 1 },
  })
  expect(line.ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })).ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/begin-receiving`, { headers })).ok()).toBeTruthy()
  const box = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  expect(box.ok()).toBeTruthy()
  const boxPayload = (await box.json()) as { id: string; internal_barcode: string }
  expect(
    (
      await page.request.post(`${INBOUND_API}/${requestId}/boxes/open`, {
        headers,
        data: { barcode: boxPayload.internal_barcode },
      })
    ).ok(),
  ).toBeTruthy()
  expect(
    (
      await page.request.post(`${INBOUND_API}/${requestId}/boxes/${boxPayload.id}/scan`, {
        headers,
        data: { barcode: sku },
      })
    ).ok(),
  ).toBeTruthy()
  return { barcode: boxPayload.internal_barcode, sku, name, productBarcode }
}

async function createForeignBoxBarcode(page: Page, suffix: string): Promise<string> {
  const foreignRegistration = await page.request.post('/api/auth/register', {
    data: {
      organization_name: 'Foreign catalog package tenant',
      slug: `foreign-catalog-package-${suffix}`,
      admin_email: `foreign-catalog-package-${suffix}@example.com`,
      password: 'password123',
    },
  })
  expect(foreignRegistration.ok()).toBeTruthy()
  const foreignToken = String(((await foreignRegistration.json()) as { access_token: string }).access_token)
  const headers = { Authorization: `Bearer ${foreignToken}` }

  const warehouse = await page.request.post('/api/warehouses', {
    headers,
    data: { name: 'Foreign warehouse', code: `foreign-catalog-${suffix}` },
  })
  expect(warehouse.ok()).toBeTruthy()
  const warehouseId = String(((await warehouse.json()) as { id: string }).id)
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name: 'Foreign product',
      sku_code: `FOREIGN-CATALOG-${suffix}`,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
    },
  })
  expect(product.ok()).toBeTruthy()
  const productId = String(((await product.json()) as { id: string }).id)
  const inbound = await page.request.post(INBOUND_API, { headers, data: { warehouse_id: warehouseId } })
  expect(inbound.ok()).toBeTruthy()
  const requestId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: productId, expected_qty: 1 },
  })
  expect(line.ok()).toBeTruthy()
  const submitted = await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })
  expect(submitted.ok()).toBeTruthy()
  const started = await page.request.post(`${INBOUND_API}/${requestId}/begin-receiving`, { headers })
  expect(started.ok()).toBeTruthy()
  const box = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  expect(box.ok()).toBeTruthy()
  return String(((await box.json()) as { internal_barcode: string }).internal_barcode)
}

async function switchToCellsStaff(page: Page, adminToken: string, suffix: string): Promise<void> {
  const adminHeaders = { Authorization: `Bearer ${adminToken}` }
  const email = `catalog-cells-${suffix}@example.com`
  const created = await page.request.post('/api/auth/staff-accounts', {
    headers: adminHeaders,
    data: { email },
  })
  expect(created.status()).toBe(201)
  const staffId = String(((await created.json()) as { id: string }).id)
  const permissions = await page.request.patch(`/api/auth/staff-accounts/${staffId}/permissions`, {
    headers: adminHeaders,
    data: { ...NO_PERMISSIONS, cells: true },
  })
  expect(permissions.ok()).toBeTruthy()
  const initialPassword = await page.request.post('/api/auth/set-initial-password', {
    data: { email, password: 'password123' },
  })
  expect(initialPassword.ok()).toBeTruthy()
  const login = await page.request.post('/api/auth/login', { data: { email, password: 'password123' } })
  expect(login.ok()).toBeTruthy()
  const staffToken = String(((await login.json()) as { access_token: string }).access_token)

  await page.evaluate((token) => {
    localStorage.setItem('wms_token_ff', token)
    localStorage.removeItem('wms_token')
  }, staffToken)
}

// TC-NEW-CATALOG-PACKAGES-001, TC-NEW-CATALOG-PACKAGES-002,
// TC-NEW-CATALOG-PACKAGES-003, TC-NEW-CATALOG-PACKAGES-004, S-16-TC-008, S-16-TC-015, S-16-TC-017.
test('catalog scan follows a received box through partial and full putaway', async ({ page }) => {
  test.setTimeout(180_000)
  const seed = await seedFfSellerInbound(page, `catalog-package-${Date.now()}`)
  const headers = { Authorization: `Bearer ${seed.token}` }
  const location = await page.request.post(`/api/warehouses/${seed.warehouseId}/locations`, {
    headers,
    data: { code: 'CATALOG-A-01' },
  })
  expect(location.ok()).toBeTruthy()

  const inbound = await page.request.post(INBOUND_API, {
    headers,
    data: { warehouse_id: seed.warehouseId },
  })
  expect(inbound.ok()).toBeTruthy()
  const requestId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: seed.productId, expected_qty: 8 },
  })
  expect(line.ok()).toBeTruthy()
  const submitted = await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })
  expect(submitted.ok()).toBeTruthy()

  await page.goto('/app/ff/reception')
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click()
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible()
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.includes('/begin-receiving')),
    page.getByTestId('ff-inbound-submit-warehouse').click(),
  ])
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Приёмка')

  await page.getByTestId('ff-inbound-packages-toggle').click()
  await page.getByTestId('ff-inbound-create-cargo-places').click()
  await expect(page.getByTestId('ff-inbound-cargo-places-dialog')).toBeVisible()
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.includes('/cargo-places')),
    page.getByTestId('ff-inbound-cargo-places-create').click(),
  ])
  const cargoBarcode = (await page.getByTestId('ff-inbound-cargo-place-row').locator('code').textContent())?.trim()
  expect(cargoBarcode).toMatch(/^ICG-/)

  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.endsWith('/boxes')),
    page.getByTestId('ff-inbound-add-to-box').click(),
  ])
  const inboundBoxes = page.getByTestId('ff-inbound-box-row')
  const firstInboundBox = inboundBoxes.first()
  const boxBarcode = (await firstInboundBox.locator('code').textContent())?.trim()
  expect(boxBarcode).toMatch(/^INB-/)
  await firstInboundBox.getByRole('button', { name: 'Наполнить' }).click()
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible()
  for (let index = 0; index < 4; index += 1) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku)
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (url) => url.includes('/boxes/') && url.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ])
  }
  await page.getByTestId('ff-inbound-box-add-dismiss').click()
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.endsWith('/boxes')),
    page.getByTestId('ff-inbound-add-to-box').click(),
  ])
  await expect(inboundBoxes).toHaveCount(2)
  const secondInboundBox = inboundBoxes.nth(1)
  const secondBoxBarcode = (await secondInboundBox.locator('code').textContent())?.trim()
  expect(secondBoxBarcode).toMatch(/^INB-/)
  expect(secondBoxBarcode).not.toBe(boxBarcode)
  await secondInboundBox.getByRole('button', { name: 'Наполнить' }).click()
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible()
  for (let index = 0; index < 4; index += 1) {
    await page.getByTestId('ff-inbound-box-add-scan-input').fill(seed.sku)
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (url) => url.includes('/boxes/') && url.includes('/scan')),
      page.getByTestId('ff-inbound-box-add-scan-submit').click(),
    ])
  }
  await page.getByTestId('ff-inbound-box-add-dismiss').click()
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (url) => url.includes('/complete-receiving')),
    page.getByTestId('ff-inbound-verify-complete').click(),
  ])
  await expect(page.getByTestId('ff-inbound-moved-to-sorting')).toBeVisible()

  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await scanCatalogPackage(page, boxBarcode!)
  const scannedBox = catalogPackageByBarcode(page, boxBarcode!)
  await expect(scannedBox).toContainText('Короб № 1')
  await expect(scannedBox.getByText(/^Приёмка №(?!\s*№)\d+$/, { exact: true })).toBeVisible()
  await expect(scannedBox).toContainText(seed.sku)
  await expect(packageQtyCell(scannedBox, seed.sku)).toHaveText('4')

  await scanCatalogPackage(page, cargoBarcode!)
  const scannedCargo = catalogPackageByBarcode(page, cargoBarcode!)
  await expect(scannedCargo).toContainText('Состав по грузоместу не ведётся')

  const foreignBarcode = await createForeignBoxBarcode(page, seed.suffix)
  for (const barcode of ['INB-UNKNOWN-CATALOG', foreignBarcode]) {
    await scanCatalogPackage(page, barcode)
    await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toHaveText(
      'Короб или грузоместо не найдено',
    )
  }

  await page.goto('/app/ff/sorting')
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click()
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible()
  const sortingRows = page.getByTestId('ff-sorting-product-card').first().getByTestId('ff-sorting-cell-row')
  await expect(sortingRows).toHaveCount(2)
  const partialRow = sortingRows.filter({
    has: page.getByTestId('ff-sorting-cell-source').filter({ hasText: 'Короб №1' }),
  })
  await expect(partialRow).toHaveCount(1)
  await partialRow.getByTestId('ff-sorting-cell-location').click()
  await page.getByRole('option', { name: /CATALOG-A-01/ }).click()
  await partialRow.getByTestId('ff-sorting-cell-qty').fill('2')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && response.url().includes('/distribution-complete') && response.ok(),
    ),
    page.getByTestId('ff-sorting-apply').click(),
  ])

  await page.goto('/app/ff/products')
  await scanCatalogPackage(page, boxBarcode!)
  await expect(packageQtyCell(catalogPackageByBarcode(page, boxBarcode!), seed.sku)).toHaveText('2')

  await page.goto('/app/ff/sorting')
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click()
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible()
  const remainingRow = page
    .getByTestId('ff-sorting-product-card')
    .first()
    .getByTestId('ff-sorting-cell-row')
    .filter({ has: page.getByTestId('ff-sorting-cell-source').filter({ hasText: 'Короб №1' }) })
  await expect(remainingRow).toHaveCount(1)
  await remainingRow.getByTestId('ff-sorting-cell-location').click()
  await page.getByRole('option', { name: /CATALOG-A-01/ }).click()
  await remainingRow.getByTestId('ff-sorting-cell-qty').fill('4')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && response.url().includes('/distribution-complete') && response.ok(),
    ),
    page.getByTestId('ff-sorting-apply').click(),
  ])
  await expect(page.getByTestId('ff-sorting-product-remaining')).toHaveText('4')

  await page.goto('/app/ff/products')
  await scanCatalogPackage(page, boxBarcode!)
  await expect(catalogPackageByBarcode(page, boxBarcode!)).toContainText('Товар из короба уже разложен')

  await page.goto('/app/ff/products')
  let listRequestCount = 0
  let releaseFailedListRequest: (() => void) | undefined
  const failedListRequestReleased = new Promise<void>((resolve) => {
    releaseFailedListRequest = resolve
  })
  let markFailedListRequestStarted: (() => void) | undefined
  const failedListRequestStarted = new Promise<void>((resolve) => {
    markFailedListRequestStarted = resolve
  })
  await page.route(/\/api\/operations\/inbound-packages$/, async (route) => {
    listRequestCount += 1
    if (listRequestCount === 1) {
      markFailedListRequestStarted?.()
      await failedListRequestReleased
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
      return
    }
    await route.continue()
  })
  await page.getByTestId('ff-catalog-inbound-packages-toggle').click()
  await failedListRequestStarted
  await expect(page.getByTestId('ff-catalog-inbound-packages-skeleton')).toBeVisible()
  await scanCatalogPackage(page, boxBarcode!)
  const distributedBox = catalogPackageByBarcode(page, boxBarcode!)
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await expect(page.getByTestId('ff-catalog-inbound-packages-skeleton')).toBeVisible()
  releaseFailedListRequest?.()
  await expect(page.getByTestId('ff-catalog-inbound-packages-error')).toBeVisible()
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        response.url().endsWith('/api/operations/inbound-packages') &&
        response.ok(),
    ),
    page.getByTestId('ff-catalog-inbound-packages-retry').click(),
  ])
  await expect(page.getByTestId('ff-catalog-inbound-packages-skeleton')).toBeHidden()
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await page.unroute(/\/api\/operations\/inbound-packages$/)

  const otherSellerBox = await createOtherSellerBox(page, seed)
  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await page.getByTestId('ff-catalog-seller-filter').click()
  await page.getByRole('option', { name: `Box Seller ${seed.suffix}`, exact: true }).click()
  await expect(page.getByTestId('ff-products-list')).toContainText(seed.sku)
  await expect(page.getByTestId('ff-products-list')).not.toContainText(otherSellerBox.sku)
  await scanCatalogPackage(page, otherSellerBox.barcode)
  const otherSellerPackage = catalogPackageByBarcode(page, otherSellerBox.barcode)
  await expect(otherSellerPackage).toContainText(otherSellerBox.sku)
  await expect(otherSellerPackage).toContainText(otherSellerBox.name)
  await expect(otherSellerPackage).toContainText(otherSellerBox.productBarcode)
  await expect(packageQtyCell(otherSellerPackage, otherSellerBox.sku)).toHaveText('1')

  await switchToCellsStaff(page, seed.token, seed.suffix)
  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-packages')).toBeVisible()
})

// S-16-TC-013, S-16-TC-016: a late network failure must enter catch without replacing the latest result or new input.
test('catalog ignores a late failed scan after the operator starts the next barcode', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `catalog-scan-race-${Date.now()}`)
  const headers = { Authorization: `Bearer ${seed.token}` }
  const inbound = await page.request.post(INBOUND_API, {
    headers,
    data: { warehouse_id: seed.warehouseId },
  })
  expect(inbound.ok()).toBeTruthy()
  const requestId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: seed.productId, expected_qty: 1 },
  })
  expect(line.ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })).ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/begin-receiving`, { headers })).ok()).toBeTruthy()

  const firstBox = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  const secondBox = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  expect(firstBox.ok()).toBeTruthy()
  expect(secondBox.ok()).toBeTruthy()
  const firstBarcode = String(((await firstBox.json()) as { internal_barcode: string }).internal_barcode)
  const secondBarcode = String(((await secondBox.json()) as { internal_barcode: string }).internal_barcode)

  let releaseFirstLookup: (() => void) | undefined
  const firstLookupReleased = new Promise<void>((resolve) => {
    releaseFirstLookup = resolve
  })
  let markFirstLookupStarted: (() => void) | undefined
  const firstLookupStarted = new Promise<void>((resolve) => {
    markFirstLookupStarted = resolve
  })
  await page.route(/\/api\/operations\/inbound-packages\/lookup/, async (route) => {
    if (route.request().url().includes(encodeURIComponent(firstBarcode))) {
      markFirstLookupStarted?.()
      await firstLookupReleased
      await route.abort('failed')
      return
    }
    await route.continue()
  })

  await page.goto('/app/ff/products')
  const search = page.getByTestId('ff-catalog-search')
  await search.fill(firstBarcode)
  const firstScan = search.press('Enter')
  await firstLookupStarted
  await scanCatalogPackage(page, secondBarcode)

  const nextBarcode = 'INB-NEXT-SCAN'
  await search.fill(nextBarcode)
  const firstLookupFailed = page.waitForEvent(
    'requestfailed',
    (request) =>
      request.method() === 'GET' &&
      request.url().includes('/api/operations/inbound-packages/lookup') &&
      request.url().includes(encodeURIComponent(firstBarcode)),
  )
  releaseFirstLookup?.()
  await firstLookupFailed
  await firstScan
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())))

  const secondPackage = page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: secondBarcode })
  await expect(secondPackage).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toBeHidden()
  await expect(search).toHaveValue(nextBarcode)
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    nextBarcode.length,
    nextBarcode.length,
  ])
})

// S-16-TC-014: a late repeated lookup must not replace the operator's next scanner input.
test('catalog deduplicates repeated scans while the first lookup is pending', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `catalog-repeat-scan-${Date.now()}`)
  const headers = { Authorization: `Bearer ${seed.token}` }
  const inbound = await page.request.post(INBOUND_API, {
    headers,
    data: { warehouse_id: seed.warehouseId },
  })
  expect(inbound.ok()).toBeTruthy()
  const requestId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: seed.productId, expected_qty: 1 },
  })
  expect(line.ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/submit`, { headers })).ok()).toBeTruthy()
  expect((await page.request.post(`${INBOUND_API}/${requestId}/begin-receiving`, { headers })).ok()).toBeTruthy()
  const box = await page.request.post(`${INBOUND_API}/${requestId}/boxes`, { headers })
  expect(box.ok()).toBeTruthy()
  const barcode = String(((await box.json()) as { internal_barcode: string }).internal_barcode)

  let releaseFirstLookup: (() => void) | undefined
  const firstLookupReleased = new Promise<void>((resolve) => {
    releaseFirstLookup = resolve
  })
  let releaseSecondLookup: (() => void) | undefined
  const secondLookupReleased = new Promise<void>((resolve) => {
    releaseSecondLookup = resolve
  })
  let lookupCount = 0
  let markFirstLookupStarted: (() => void) | undefined
  const firstLookupStarted = new Promise<void>((resolve) => {
    markFirstLookupStarted = resolve
  })
  let markSecondLookupStarted: (() => void) | undefined
  const secondLookupStarted = new Promise<void>((resolve) => {
    markSecondLookupStarted = resolve
  })
  await page.route(/\/api\/operations\/inbound-packages\/lookup/, async (route) => {
    if (!route.request().url().includes(encodeURIComponent(barcode))) {
      await route.continue()
      return
    }
    lookupCount += 1
    if (lookupCount === 1) {
      markFirstLookupStarted?.()
      await firstLookupReleased
    } else {
      markSecondLookupStarted?.()
      await secondLookupReleased
    }
    await route.continue()
  })

  await page.goto('/app/ff/products')
  const search = page.getByTestId('ff-catalog-search')
  await search.fill(barcode)
  const firstScan = search.press('Enter')
  await firstLookupStarted
  await search.fill(barcode)
  const secondScan = search.press('Enter')
  await secondLookupStarted

  const secondLookupResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      response.url().includes('/api/operations/inbound-packages/lookup') &&
      response.url().includes(encodeURIComponent(barcode)) &&
      response.ok(),
  )
  releaseSecondLookup?.()
  await secondLookupResponse
  await secondScan
  await expect(catalogPackageByBarcode(page, barcode)).toHaveCount(1)
  await expect(catalogPackageByBarcode(page, barcode)).toBeVisible()
  await expect(search).toBeFocused()
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    barcode.length,
    barcode.length,
  ])

  const nextBarcode = 'INB-NEXT-SCAN'
  await search.selectText()
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    0,
    barcode.length,
  ])
  await search.pressSequentially(nextBarcode)
  await expect(search).toHaveValue(nextBarcode)
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    nextBarcode.length,
    nextBarcode.length,
  ])

  const firstLookupResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      response.url().includes('/api/operations/inbound-packages/lookup') &&
      response.url().includes(encodeURIComponent(barcode)) &&
      response.ok(),
  )
  releaseFirstLookup?.()
  await firstLookupResponse
  await firstScan
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())))
  await expect(catalogPackageByBarcode(page, barcode)).toHaveCount(1)
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toBeHidden()
  await expect(search).toBeFocused()
  await expect(search).toHaveValue(nextBarcode)
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    nextBarcode.length,
    nextBarcode.length,
  ])

  await search.pressSequentially('-CONTINUED')
  await expect(search).toHaveValue(`${nextBarcode}-CONTINUED`)
})
