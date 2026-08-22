import { expect, test } from '@playwright/test'

import { loginSellerPortal, seedFfSellerInbound } from './inbound-boxes-helpers'

// TC-NEW-F07-014 — the seller report keeps the shared report layout but never
// exposes the FF-only seller scope or technical legacy-data warning.
test('seller reports hide FF-only seller filter and technical warning', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `seller-reports-${Date.now()}`)
  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    const response = await route.fetch()
    const rows = (await response.json()) as { id: string; name: string; code: string }[]
    await route.fulfill({
      response,
      contentType: 'application/json',
      body: JSON.stringify([
        ...rows,
        {
          id: 'service-fbs-archive',
          name: 'FBS WB Архив',
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
  await expect(page.getByTestId('ff-reports-warehouse')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-warning')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-metrics')).toBeVisible()
  await expect(page.getByTestId('ff-reports-chart')).toBeVisible()
})
