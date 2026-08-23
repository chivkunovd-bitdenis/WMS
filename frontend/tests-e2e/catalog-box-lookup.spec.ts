import { expect, test, type Page } from '@playwright/test'

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
// TC-NEW-CATALOG-PACKAGES-003, TC-NEW-CATALOG-PACKAGES-004, S-16-TC-015.
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
    data: { product_id: seed.productId, expected_qty: 4 },
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
  const inboundBox = page.getByTestId('ff-inbound-box-row').first()
  const boxBarcode = (await inboundBox.locator('code').textContent())?.trim()
  expect(boxBarcode).toMatch(/^INB-/)
  await inboundBox.getByRole('button', { name: 'Наполнить' }).click()
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
  const scannedBox = page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: boxBarcode! })
  await expect(scannedBox).toContainText('Короб № 1')
  await expect(scannedBox).toContainText(seed.sku)
  await expect(scannedBox).toContainText('4')

  await scanCatalogPackage(page, cargoBarcode!)
  const scannedCargo = page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: cargoBarcode! })
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
  const partialRow = page.getByTestId('ff-sorting-product-card').first().getByTestId('ff-sorting-cell-row').first()
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
  await expect(page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: boxBarcode! })).toContainText('2')

  await page.goto('/app/ff/sorting')
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click()
  await expect(page.getByTestId('ff-sorting-panel')).toBeVisible()
  const remainingRow = page.getByTestId('ff-sorting-product-card').first().getByTestId('ff-sorting-cell-row').first()
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
  const distributedBox = page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: boxBarcode! })
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await expect(page.getByTestId('ff-catalog-inbound-packages-skeleton')).toBeVisible()
  releaseFailedListRequest?.()
  await expect(page.getByTestId('ff-catalog-inbound-packages-error')).toBeVisible()
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await page.getByTestId('ff-catalog-inbound-packages-retry').click()
  await expect(distributedBox).toContainText('Товар из короба уже разложен')
  await page.unroute(/\/api\/operations\/inbound-packages$/)

  await switchToCellsStaff(page, seed.token, seed.suffix)
  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-packages')).toBeVisible()
})

// S-16-TC-013, S-16-TC-016: a late failed scan must not replace the latest result or select new input.
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
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
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
  releaseFirstLookup?.()
  await firstScan

  const secondPackage = page.locator('[data-testid^="ff-catalog-inbound-package-"]').filter({ hasText: secondBarcode })
  await expect(secondPackage).toBeVisible()
  await expect(page.getByTestId('ff-catalog-inbound-packages-lookup-error')).toBeHidden()
  await expect(search).toHaveValue(nextBarcode)
  await expect.poll(() => search.evaluate((input) => [input.selectionStart, input.selectionEnd])).toEqual([
    nextBarcode.length,
    nextBarcode.length,
  ])
})
