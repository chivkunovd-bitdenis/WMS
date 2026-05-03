import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-001 — FF складской каталог: только товары с движениями ФФ.
// Given: FF admin, есть товары селлеров, но один товар не принимался на склад; When: открывает «Товары»;
// Then: видны только товары с движениями, остаток равен actual_qty; restriction/negative: private-only товар не виден ФФ.
test('ff products: filter by seller and sort by name/quantity', async ({ page }) => {
  const email = `e2e-ff-products-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Products')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await expect(page.getByTestId('dashboard')).toBeVisible()

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token'))) ?? ''
  expect(regToken).toBeTruthy()
  const h = { Authorization: `Bearer ${regToken}` }

  async function apiPost(path: string, data: Record<string, unknown>) {
    const res = await page.request.post(`/api${path}`, { headers: h, data })
    if (!res.ok()) {
      throw new Error(`POST ${path} failed: ${res.status()} ${await res.text()}`)
    }
    return res
  }

  async function apiPatch(path: string, data: Record<string, unknown>) {
    const res = await page.request.patch(`/api${path}`, { headers: h, data })
    if (!res.ok()) {
      throw new Error(`PATCH ${path} failed: ${res.status()} ${await res.text()}`)
    }
    return res
  }

  // Seed: 2 sellers + products; one product stays private-only with no FF movement.
  const sellerA = (await (await apiPost('/sellers', { name: 'E2E Seller A' })).json()) as { id: string }
  const sellerB = (await (await apiPost('/sellers', { name: 'E2E Seller B' })).json()) as { id: string }

  const skuA = `e2e-ff-a-${Date.now()}`
  const skuB = `e2e-ff-b-${Date.now()}`
  const skuPrivate = `e2e-ff-private-${Date.now()}`
  const prodA = (await (
    await apiPost('/products', {
      name: 'Alpha product',
      sku_code: skuA,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerA.id,
    })
  ).json()) as { id: string }
  const prodB = (await (
    await apiPost('/products', {
      name: 'Beta product',
      sku_code: skuB,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerB.id,
    })
  ).json()) as { id: string }
  await apiPost('/products', {
    name: 'Private only product',
    sku_code: skuPrivate,
    length_mm: 1,
    width_mm: 1,
    height_mm: 1,
    seller_id: sellerA.id,
  })

  // Put different stock totals via inbound receive so sorting by остаток is meaningful.
  const whCode = `e2e-wh-${Date.now()}`
  const wh = (await (await apiPost('/warehouses', { name: 'E2E WH', code: whCode })).json()) as { id: string }
  const loc = (await (await apiPost(`/warehouses/${wh.id}/locations`, { code: 'A-01' })).json()) as {
    id: string
  }

  async function inboundReceive(productId: string, expectedQty: number, actualQty: number) {
    const createReq = await apiPost('/operations/inbound-intake-requests', {
      warehouse_id: wh.id,
      planned_delivery_date: new Date().toISOString().slice(0, 10),
    })
    const req = (await createReq.json()) as { id: string }
    const addLineRes = await apiPost(`/operations/inbound-intake-requests/${req.id}/lines`, {
      product_id: productId,
      expected_qty: expectedQty,
    })
    const line = (await addLineRes.json()) as { id: string }
    await apiPost(`/operations/inbound-intake-requests/${req.id}/submit`, {})
    await apiPost(`/operations/inbound-intake-requests/${req.id}/primary-accept`, {})
    await apiPatch(`/operations/inbound-intake-requests/${req.id}/lines/${line.id}`, {
      storage_location_id: loc.id,
    })
    await apiPatch(`/operations/inbound-intake-requests/${req.id}/lines/${line.id}/actual`, {
      actual_qty: actualQty,
    })
    await apiPost(`/operations/inbound-intake-requests/${req.id}/verify`, {})
    await apiPost(`/operations/inbound-intake-requests/${req.id}/post`, {})
  }

  await inboundReceive(prodA.id, 10, 2)
  await inboundReceive(prodB.id, 10, 5)

  // Reload so App re-fetches sellers list for the filter dropdown.
  await page.reload()
  await expect(page.getByTestId('dashboard')).toBeVisible()

  // Go to FF products screen
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-products-table')).toBeVisible()

  // Filter by seller A
  await page.getByTestId('ff-products-seller-filter').click()
  const sellerListbox = page.getByRole('listbox')
  await expect(sellerListbox).toBeVisible()
  await sellerListbox.getByText('E2E Seller A', { exact: true }).click()
  await expect(page.getByTestId('ff-product-row')).toHaveCount(1)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuA)
  await expect(page.getByTestId('ff-products-table')).not.toContainText(skuPrivate)
  await expect(page.getByTestId('ff-product-row').first().locator('td').nth(7)).toHaveText('2')

  // Switch to All
  await page.getByTestId('ff-products-seller-filter').click()
  await expect(sellerListbox).toBeVisible()
  await sellerListbox.getByText('Все', { exact: true }).click()
  await expect(page.getByTestId('ff-product-row')).toHaveCount(2)

  // Sort by quantity desc: first row should be product B (qty 5)
  await page.getByTestId('ff-products-sort-quantity').click()
  await page.getByTestId('ff-products-sort-quantity').click()
  const firstSkuAfterQty = await page.getByTestId('ff-product-row').first().locator('td').nth(1).innerText()
  expect(firstSkuAfterQty).toContain(skuB)

  // Sort by name asc: Alpha first
  await page.getByTestId('ff-products-sort-name').click()
  const firstNameAfterName = await page.getByTestId('ff-product-row').first().locator('td').nth(5).innerText()
  expect(firstNameAfterName).toContain('Alpha')

  // Photo cell exists (even if WB photo missing in mocks): first column rendered and has avatar element.
  await expect(page.getByTestId('ff-product-row').first().locator('td').first()).toBeVisible()
})

