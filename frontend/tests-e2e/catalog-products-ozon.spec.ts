import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

test('catalog products: filter works before search and Ozon link is edited in the SKU card', async ({ page }) => {
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
  const wbSeller = await page.request.post('/api/sellers', { headers, data: { name: 'WB-only seller' } })
  expect(seller.ok()).toBeTruthy()
  expect(wbSeller.ok()).toBeTruthy()
  const sellerId = (await seller.json()).id
  const wbSellerId = (await wbSeller.json()).id
  const sellerEmail = `e2e-catalog-ozon-seller-${stamp}@example.com`
  const sellerAccount = await page.request.post('/api/auth/seller-accounts', {
    headers,
    data: { seller_id: sellerId, email: sellerEmail, password: 'password123' },
  })
  expect(sellerAccount.ok()).toBeTruthy()
  const sellerLogin = await page.request.post('/api/auth/login', {
    data: { email: sellerEmail, password: 'password123' },
  })
  expect(sellerLogin.ok()).toBeTruthy()
  const sellerToken = (await sellerLogin.json()).access_token
  const ozonAccount = await page.request.put('/api/integrations/ozon/self/account', {
    headers: { Authorization: `Bearer ${sellerToken}` },
    data: { client_id: 'e2e-client', api_key: 'e2e-key' },
  })
  expect(ozonAccount.ok()).toBeTruthy()
  const ozonSku = `OZON-S31-${stamp}`
  const product = await page.request.post('/api/products', {
    headers,
    data: {
      name: 'S31 Ozon product', sku_code: `S31-${stamp}`, seller_id: sellerId,
      length_mm: 1, width_mm: 1, height_mm: 1, ozon_sku: ozonSku, ozon_offer_id: `OFFER-${stamp}`,
    },
  })
  expect(product.ok()).toBeTruthy()
  const editable = await page.request.post('/api/products', {
    headers,
    data: {
      name: 'S31 existing WMS product', sku_code: `EDIT-${stamp}`, seller_id: sellerId,
      length_mm: 1, width_mm: 1, height_mm: 1,
    },
  })
  const wbOnly = await page.request.post('/api/products', {
    headers,
    data: {
      name: 'S31 WB-only product', sku_code: `WB-${stamp}`, seller_id: wbSellerId,
      length_mm: 1, width_mm: 1, height_mm: 1, wb_vendor_code: `WB-OFFER-${stamp}`,
    },
  })
  expect(editable.ok()).toBeTruthy()
  expect(wbOnly.ok()).toBeTruthy()
  const editableId = (await editable.json()).id
  await page.goto('/app/catalog/products')
  await expect(page.getByTestId('product-table')).toBeVisible()

  await page.getByTestId('products-marketplace-filter').selectOption('ozon')
  await expect(page.getByLabel('Поиск SKU')).toHaveValue('')
  await expect(page.getByTestId('product-item')).toHaveCount(1)
  await expect(page.getByTestId('product-item')).toContainText('S31 Ozon product')
  await page.screenshot({
    path: '../docs/evidence/ozon-integration-20260825/S-31/catalog-ozon-filter-before-search.png',
    fullPage: true,
  })
  await page.getByLabel('Поиск SKU').fill(ozonSku)
  const row = page.getByTestId('product-item').filter({ hasText: 'S31 Ozon product' })
  await expect(row).toBeVisible()
  await expect(row.getByTestId('product-marketplace-ozon')).toHaveText('Ozon')
  await row.click()
  await expect(page.getByTestId('product-ozon-link')).toContainText(ozonSku)

  await page.getByLabel('Поиск SKU').fill('')
  await page.getByTestId('products-marketplace-filter').selectOption('')
  const wbRow = page.getByTestId('product-item').filter({ hasText: 'S31 WB-only product' })
  await wbRow.click()
  await expect(page.getByTestId('product-ozon-link-form')).toHaveCount(0)
  await expect(page.getByTestId('products-marketplace-filter')).toBeVisible()

  const editableRow = page.getByTestId('product-item').filter({ hasText: 'S31 existing WMS product' })
  await editableRow.click()
  await expect(page.getByTestId('product-ozon-link-form')).toBeVisible()
  const updatedSku = `UPDATED-OZON-${stamp}`
  await page.getByTestId('product-link-ozon-sku').fill(updatedSku)
  await page.getByTestId('product-link-ozon-offer').fill(`UPDATED-OFFER-${stamp}`)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes(`/api/products/${editableId}/ozon-link`) && response.ok()),
    page.getByTestId('product-link-ozon-submit').click(),
  ])
  await expect(page.getByTestId('product-ozon-link')).toContainText(updatedSku)
  await page.screenshot({
    path: '../docs/evidence/ozon-integration-20260825/S-31/catalog-ozon-correction.png',
    fullPage: true,
  })
})
