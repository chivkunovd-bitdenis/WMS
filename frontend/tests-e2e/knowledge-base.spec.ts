import { expect, test } from '@playwright/test'

import {
  loginFfAdmin,
  loginSellerPortal,
  seedFfSellerInbound,
} from './inbound-boxes-helpers'

test('inbound knowledge guide is available to seller and FF', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `knowledge-${Date.now()}`)

  await loginSellerPortal(page, seed.sellerEmail, seed.password)
  await page.getByTestId('nav-seller-knowledge').click()
  await expect(page).toHaveURL(/\/seller\/knowledge$/)
  await expect(page.getByTestId('knowledge-base-page')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Создание приёмки: от селлера до ФФ' })).toBeVisible()
  await expect(page.getByTestId(/^knowledge-step-\d$/)).toHaveCount(4)
  await expect(page.getByTestId(/^knowledge-step-callout-\d$/)).toHaveCount(4)
  await expect(page.getByTestId(/^knowledge-step-image-\d$/)).toHaveCount(4)

  const imagesLoaded = await page.getByTestId(/^knowledge-step-image-\d$/).evaluateAll((images) =>
    images.every((image) => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0),
  )
  expect(imagesLoaded).toBe(true)

  await expect(page.getByTestId('knowledge-open-workflow')).toHaveText('Открыть документы')
  await page.getByTestId('knowledge-open-workflow').click()
  await expect(page).toHaveURL(/\/seller\/documents$/)

  await loginFfAdmin(page, seed.adminEmail, seed.password)
  await page.getByTestId('nav-ff-knowledge').click()
  await expect(page).toHaveURL(/\/app\/ff\/knowledge$/)
  await expect(page.getByTestId('knowledge-base-page')).toBeVisible()
  await expect(page.getByTestId('knowledge-open-workflow')).toHaveText('Открыть приёмку')
  await page.getByTestId('knowledge-open-workflow').click()
  await expect(page).toHaveURL(/\/app\/ff\/reception$/)
  await expect(page.getByTestId('ff-reception-page')).toBeVisible()
})
