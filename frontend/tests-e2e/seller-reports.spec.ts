import { expect, test } from '@playwright/test'

import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  INBOUND_API,
  loginSellerPortal,
  sellerPath,
  seedFfSellerInbound,
} from './inbound-boxes-helpers'
import { loginAsSeller } from './auth-flow'

// S-33-TC-016 — Given seller staff with documents access but without
// can_products, When they open the report route directly, Then the seller
// portal shows access denied and does not request or render reporting data.
// The registry route is /app/seller/reports; local Playwright mounts the same
// SellerApp under /seller, so sellerPath('/reports') resolves to /seller/reports.
test('seller staff without products access cannot open the direct reports route', async ({ page }) => {
  const suffix = `seller-reports-denied-${Date.now()}`
  const seed = await seedFfSellerInbound(page, suffix)
  const staffEmail = `${suffix}@example.com`

  await page.getByTestId('logout').click()
  await loginSellerPortal(page, seed.sellerEmail, seed.password)
  await page.getByTestId('nav-seller-settings').click()
  await expect(page.getByTestId('seller-staff-panel')).toBeVisible()
  await page.getByTestId('seller-staff-email').fill(staffEmail)
  await page.getByTestId('seller-staff-create-perm-products').click()
  await page.getByTestId('seller-staff-create-perm-honest_sign').click()
  await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes('/api/auth/seller-staff-accounts') &&
      response.request().method() === 'POST' &&
      response.ok(),
    ),
    page.waitForResponse((response) =>
      response.url().includes('/api/auth/seller-staff-accounts') &&
      response.request().method() === 'GET' &&
      response.ok(),
    ),
    page.getByTestId('seller-staff-submit').click(),
  ])
  await expect(page.getByTestId('seller-staff-row').filter({ hasText: staffEmail })).toBeVisible()

  await page.getByTestId('logout').click()
  await loginAsSeller(page, staffEmail, seed.password, { firstTime: true })
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible()
  await expect(page.getByTestId('nav-seller-reports')).toHaveCount(0)

  let reportRequests = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/reports/')) reportRequests += 1
  })
  const directReportsPath = sellerPath('/reports')
  await page.goto(directReportsPath)

  await expect.poll(() => new URL(page.url()).pathname).toBe(directReportsPath)
  await expect(page.getByTestId('seller-access-denied')).toContainText(
    'Нет доступа к этому разделу. Обратитесь к администратору селлера.',
  )
  await expect(page.getByTestId('ff-reports-page')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-metrics')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-chart')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-table')).toHaveCount(0)
  expect(reportRequests).toBe(0)
})

// S-33-TC-003 / S-33-TC-014 — only the API operational flag defines the seller
// report warehouses, while the authenticated seller scope excludes other data.
test('seller reports exclude non-operational warehouses and other seller data', async ({ page }) => {
  test.setTimeout(90_000)
  const suffix = `seller-reports-${Date.now()}`
  const seed = await seedFfSellerInbound(page, suffix)
  const adminHeaders = { Authorization: `Bearer ${seed.token}` }
  const otherSellerEmail = `other-${suffix}@example.com`
  const otherSku = `other-seller-sku-${suffix}`

  const otherSellerResponse = await page.request.post('/api/sellers', {
    headers: adminHeaders,
    data: { name: 'Other report seller' },
  })
  expect(otherSellerResponse.ok()).toBeTruthy()
  const otherSellerId = String(
    ((await otherSellerResponse.json()) as { id: string }).id,
  )
  const otherAccountResponse = await page.request.post('/api/auth/seller-accounts', {
    headers: adminHeaders,
    data: {
      seller_id: otherSellerId,
      email: otherSellerEmail,
      password: seed.password,
    },
  })
  expect(otherAccountResponse.ok()).toBeTruthy()
  const otherProductResponse = await page.request.post('/api/products', {
    headers: adminHeaders,
    data: {
      name: 'Other seller report product',
      sku_code: otherSku,
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
      seller_id: otherSellerId,
    },
  })
  expect(otherProductResponse.ok()).toBeTruthy()
  const otherProductId = String(
    ((await otherProductResponse.json()) as { id: string }).id,
  )

  const reportSeeds = [
    seed,
    {
      ...seed,
      sellerEmail: otherSellerEmail,
      sellerId: otherSellerId,
      productId: otherProductId,
      sku: otherSku,
    },
  ]
  for (const [index, reportSeed] of reportSeeds.entries()) {
    const requestId = await apiCreateSubmittedInbound(page.request, reportSeed, {
      plannedBoxes: 1,
      expectedQty: index + 2,
    })
    const { boxes } = await beginInboundReceivingWithBoxes(
      page.request,
      adminHeaders,
      requestId,
      { boxCount: 1 },
    )
    await fulfillInboundViaBoxScans(
      page.request,
      adminHeaders,
      requestId,
      boxes,
      reportSeed.sku,
      [index + 2],
    )
    const verifyResponse = await page.request.post(`${INBOUND_API}/${requestId}/verify`, {
      headers: adminHeaders,
    })
    expect(verifyResponse.ok()).toBeTruthy()
    const postResponse = await page.request.post(`${INBOUND_API}/${requestId}/post`, {
      headers: adminHeaders,
    })
    expect(postResponse.ok()).toBeTruthy()
  }

  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: seed.warehouseId,
          name: 'Основной склад',
          code: 'main-reporting',
          is_operational: true,
        },
        {
          id: 'service-fbs-archive',
          name: 'Архив',
          code: 'fbs-wb-archive',
          is_operational: false,
        },
      ]),
    })
  })

  await loginSellerPortal(page, seed.sellerEmail, seed.password)
  await page.getByTestId('nav-seller-reports').click()

  await expect(page).toHaveURL('/app/seller/reports')
  await expect(page.getByTestId('ff-reports-page')).toBeVisible()
  await expect(page.getByTestId('ff-reports-seller')).toHaveCount(0)
  await expect(page.getByRole('option', { name: 'Архив' })).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-warehouse')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-warning')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-metrics')).toBeVisible()
  await expect(page.getByTestId('ff-reports-chart')).toBeVisible()
  await expect(page.getByTestId('ff-reports-table')).toContainText(seed.sku)
  await expect(page.getByTestId('ff-reports-table')).not.toContainText(otherSku)
})
