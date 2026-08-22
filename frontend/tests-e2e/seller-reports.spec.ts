import { expect, test } from '@playwright/test'

import { loginSellerPortal, seedFfSellerInbound } from './inbound-boxes-helpers'

// TC-NEW-F07-014 — the seller report keeps the shared report layout but never
// exposes the FF-only seller scope or technical legacy-data warning.
test('seller reports hide FF-only seller filter and technical warning', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `seller-reports-${Date.now()}`)

  await loginSellerPortal(page, seed.sellerEmail, seed.password)
  await page.getByTestId('nav-seller-reports').click()

  await expect(page.getByTestId('ff-reports-page')).toBeVisible()
  await expect(page.getByTestId('ff-reports-seller')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-warning')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-metrics')).toBeVisible()
  await expect(page.getByTestId('ff-reports-chart')).toBeVisible()
})
