import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

async function registerAdmin(page: import('@playwright/test').Page, stamp: number) {
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Catalog Ozon')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(`e2e-catalog-ozon-${stamp}@example.com`)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  return { Authorization: `Bearer ${token}` }
}

async function createProduct(
  page: import('@playwright/test').Page,
  headers: Record<string, string>,
  sellerId: string,
  name: string,
  sku: string,
  wbVendorCode?: string,
) {
  const response = await page.request.post('/api/products', {
    headers,
    data: {
      name,
      sku_code: sku,
      seller_id: sellerId,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      ...(wbVendorCode ? { wb_vendor_code: wbVendorCode } : {}),
    },
  })
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as { id: string }
}

test('S-16: server marketplace filter and warehouse-only Ozon binding feedback', async ({ page }) => {
  const stamp = Date.now()
  const headers = await registerAdmin(page, stamp)
  const seller = await page.request.post('/api/sellers', { headers, data: { name: 'Catalog seller' } })
  expect(seller.ok()).toBeTruthy()
  const sellerId = String(((await seller.json()) as { id: string }).id)
  const linked = await createProduct(page, headers, sellerId, 'Already linked', `LINKED-${stamp}`, `WB-LINKED-${stamp}`)
  const editable = await createProduct(page, headers, sellerId, 'Warehouse editable', `EDIT-${stamp}`, `WB-EDIT-${stamp}`)
  const duplicateSku = `OZON-DUP-${stamp}`
  const link = await page.request.patch(`/api/products/${linked.id}/ozon-link`, {
    headers,
    data: { ozon_sku: duplicateSku, ozon_offer_id: `OFFER-DUP-${stamp}` },
  })
  expect(link.ok()).toBeTruthy()

  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-table')).toBeVisible()
  const filterResponse = page.waitForResponse((response) =>
    response.url().includes('/api/products/ff-catalog?marketplace=ozon') && response.ok(),
  )
  await page.getByTestId('ff-catalog-marketplace-filter').click()
  await page.getByRole('option', { name: 'Ozon', exact: true }).click()
  await filterResponse
  const linkedRow = page.getByTestId('ff-product-row').filter({ hasText: 'Already linked' })
  await expect(linkedRow).toBeVisible()
  await expect(linkedRow).toContainText(`WB-LINKED-${stamp}`)
  await expect(linkedRow.getByTestId('ff-catalog-marketplace-ozon')).toHaveText('Ozon')

  await page.getByTestId('ff-catalog-marketplace-filter').click()
  await page.getByRole('option', { name: 'Все', exact: true }).click()
  const editableRow = page.getByTestId('ff-product-row').filter({ hasText: 'Warehouse editable' })
  await editableRow.getByTestId(`ff-packaging-edit-${editable.id}`).click()
  await page.getByTestId('ff-product-ozon-sku').fill(duplicateSku)
  await page.getByTestId('ff-product-ozon-offer').fill(`EDIT-OFFER-${stamp}`)
  await page.getByTestId('ff-packaging-save').click()
  await expect(page.getByTestId('ff-ozon-link-error')).toHaveText('Этот SKU уже привязан к другому товару.')

  const uniqueSku = `OZON-UNIQUE-${stamp}`
  await page.getByTestId('ff-product-ozon-sku').fill(uniqueSku)
  await page.getByTestId('ff-packaging-save').click()
  await expect(page.getByTestId('ff-products-import-notice')).toContainText('Привязка Ozon')
  await page.screenshot({
    path: '../docs/evidence/ozon-integration-20260825/S-16/live-browser-corrected.png',
    fullPage: true,
  })
})

test('S-31: seller sees Ozon chip in Name and never receives binding controls', async ({ page }) => {
  const stamp = Date.now()
  const headers = await registerAdmin(page, stamp)
  const seller = await page.request.post('/api/sellers', { headers, data: { name: 'Seller portal catalog' } })
  expect(seller.ok()).toBeTruthy()
  const sellerId = String(((await seller.json()) as { id: string }).id)
  const ozonProduct = await createProduct(page, headers, sellerId, 'Ozon visible item', `OZON-ITEM-${stamp}`)
  await createProduct(page, headers, sellerId, 'WB visible item', `WB-ITEM-${stamp}`, `WB-OFFER-${stamp}`)
  const ozonSku = `OZON-S31-${stamp}`
  const link = await page.request.patch(`/api/products/${ozonProduct.id}/ozon-link`, {
    headers,
    data: { ozon_sku: ozonSku, ozon_offer_id: `OZON-OFFER-${stamp}` },
  })
  expect(link.ok()).toBeTruthy()
  const sellerEmail = `e2e-seller-catalog-${stamp}@example.com`
  const account = await page.request.post('/api/auth/seller-accounts', {
    headers,
    data: { seller_id: sellerId, email: sellerEmail, password: 'password123' },
  })
  expect(account.ok()).toBeTruthy()

  await loginAsSeller(page, sellerEmail, 'password123', { firstTime: false })
  await page.goto('/seller/products')
  await expect(page.getByTestId('seller-products-table')).toBeVisible()
  const ozonRow = page.getByTestId('seller-product-row').filter({ hasText: 'Ozon visible item' })
  await expect(ozonRow).toContainText('Ozon visible item')
  await expect(ozonRow.getByTestId('seller-catalog-marketplace-ozon')).toHaveText('Ozon')
  // A durable product link keeps its chip even when the Ozon cabinet is not
  // connected. The marketplace filter, unlike the chip, requires two live
  // connections and therefore stays hidden in this scenario.
  await expect(page.getByTestId('seller-catalog-marketplace-filter')).toHaveCount(0)
  await expect(page.getByText('Сохранить Ozon', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('SKU Ozon')).toHaveCount(0)
  await page.screenshot({
    path: '../docs/evidence/ozon-integration-20260825/S-31/live-browser-corrected.png',
    fullPage: true,
  })
})
