import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

test('catalog products: Ozon link is searchable, filterable, and shown beside WB details', async ({ page }) => {
  const stamp = Date.now()
  const email = `e2e-catalog-ozon-${stamp}@example.com`
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Catalog Ozon')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const headers = { Authorization: `Bearer ${token}` }
  const seller = await page.request.post('/api/sellers', { headers, data: { name: 'Catalog Ozon seller' } })
  expect(seller.ok()).toBeTruthy()
  const ozonSku = `OZON-S31-${stamp}`
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name: 'S31 Ozon product', sku_code: `S31-${stamp}`, seller_id: (await seller.json()).id,
      length_mm: 1, width_mm: 1, height_mm: 1, ozon_sku: ozonSku, ozon_offer_id: `OFFER-${stamp}`,
    },
  })
  expect(product.ok()).toBeTruthy()
  await page.goto('/app/catalog/products')
  await expect(page.getByTestId('product-table')).toBeVisible()
  await page.getByTestId('products-marketplace-filter').selectOption('ozon')
  await page.getByLabel('Поиск SKU').fill(ozonSku)
  const row = page.getByTestId('product-item').filter({ hasText: 'S31 Ozon product' })
  await expect(row).toBeVisible()
  await expect(row.getByTestId('product-marketplace-ozon')).toHaveText('Ozon')
  await row.click()
  await expect(page.getByTestId('product-ozon-link')).toContainText(ozonSku)
})
