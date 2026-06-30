import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk, waitForPutOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { seedHonestSignProductFirstInventory, selectHonestSignSeller } from './ff-honest-sign-helpers'

// TC-NEW-E2E01-001 — E2E-01: product-first navigation list → product → shared pool; no personal double-count.
// TC-NEW-API01-001 — inventory personal_available + shared_baskets (UI regression).
// TC-NEW-API01-002 — marking-overview personal vs shared (UI regression).
// TC-NEW-POOL01-001 — shared pool badge «Общая корзина · на N товаров» (UI regression).
test('FF honest sign product-first: list, product card, shared basket pool', async ({ page }) => {
  test.setTimeout(180_000)
  const email = `e2e-hs-pf-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const skuPrefix = `HS-PF-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E HS Product First')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const bearer = { Authorization: `Bearer ${token}` }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E HS PF Seller', email: `hs-pf-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const { personalPoolId, sharedPoolId, productX } = await seedHonestSignProductFirstInventory(
    page,
    e2eApi,
    auth,
    bearer,
    sellerId,
    skuPrefix,
  )

  // Step 1 — /honest-sign: product X personal 100 + basket chip; KPI without double-count.
  await page.getByTestId('nav-ff-honest-sign').click()
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible()
  await selectHonestSignSeller(page, sellerId)

  const productRow = page.getByTestId(`ff-honest-sign-product-row-${productX.id}`)
  await expect(productRow).toBeVisible()
  await expect(productRow).toContainText(productX.sku_code)
  await expect(productRow).toContainText('100')

  const basketChip = page.getByTestId(`ff-honest-sign-product-basket-${productX.id}-${sharedPoolId}`)
  await expect(basketChip).toBeVisible()
  await expect(basketChip).toContainText('на 3 тов.')
  await expect(basketChip).toContainText('1000')
  await expect(page.getByTestId('ff-honest-sign-kpi-available')).toContainText('100')
  await expect(productRow).not.toContainText('1100')

  // Step 2 — click product X → card with personal pool + shared basket B.
  await productRow.click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/product/${productX.id}`))
  await expect(page.getByTestId('ff-honest-sign-product-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-product-personal-available')).toHaveText('100')
  await expect(page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolId}`)).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolId}`)).toContainText(
    'Personal A',
  )
  await expect(page.getByTestId(`ff-honest-sign-product-shared-basket-${sharedPoolId}`)).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-product-shared-basket-${sharedPoolId}`)).toContainText('Shared B')

  // Step 3 — click basket B → pool card with shared badge.
  await page.getByTestId(`ff-honest-sign-product-shared-basket-${sharedPoolId}`).click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/pool/${sharedPoolId}`))
  await expect(page.getByTestId('ff-honest-sign-pool-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-shared-badge')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-shared-badge')).toContainText(
    'Общая корзина · на 3 товаров',
  )
})

// TC-STAB-CZ-FE-01 — multi-pool product: per-pool threshold is configured from product page.
test('FF honest sign multi-pool product: product page threshold persists after reload', async ({ page }) => {
  test.setTimeout(180_000)
  const email = `e2e-hs-mp-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const skuPrefix = `HS-MP-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E HS Multi Pool')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const bearer = { Authorization: `Bearer ${token}` }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E HS MP Seller', email: `hs-mp-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Multi Pool Product',
      sku_code: `${skuPrefix}-M`,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(productRes.ok()).toBeTruthy()
  const product = (await productRes.json()) as { id: string }

  async function importPersonalPool(title: string, gtin: string, serialChar: string): Promise<string> {
    const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
      headers: bearer,
      multipart: {
        seller_id: sellerId,
        pools_json: JSON.stringify([
          { title, gtin, product_ids: [product.id] },
        ]),
        files: {
          name: `${gtin}.csv`,
          mimeType: 'text/csv',
          buffer: Buffer.from(`cis\n01${gtin}21${serialChar.repeat(16)}0001`),
        },
      },
    })
    expect(imp.ok()).toBeTruthy()
    return String(((await imp.json()) as { pools: { pool_id: string }[] }).pools[0].pool_id)
  }

  const personalPoolA = await importPersonalPool('Personal A', '04600000000011', 'A')
  const personalPoolB = await importPersonalPool('Personal B', '04600000000012', 'B')

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await page.goto(`/app/ff/honest-sign/product/${product.id}`)
  await expect(page.getByTestId('ff-honest-sign-product-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-product-threshold')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-product-threshold-pool')).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolA}`)).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolB}`)).toBeVisible()

  await page.getByTestId('ff-honest-sign-product-threshold-pool').click()
  await page.getByRole('option', { name: 'Personal A' }).click()
  await page.getByTestId('ff-honest-sign-product-threshold-low').locator('input').fill('42')
  await page.getByTestId('ff-honest-sign-product-threshold-forecast-days').locator('input').fill('7')
  await Promise.all([
    waitForPutOk(page, `/api/operations/marking-codes/pools/${personalPoolA}/threshold`),
    page.getByTestId('ff-honest-sign-product-threshold-save').click(),
  ])

  await page.reload()
  await page.getByTestId('ff-honest-sign-product-threshold-pool').click()
  await page.getByRole('option', { name: 'Personal A' }).click()
  await expect(page.getByTestId('ff-honest-sign-product-threshold-low').locator('input')).toHaveValue('42')
  await expect(page.getByTestId('ff-honest-sign-product-threshold-forecast-days').locator('input')).toHaveValue('7')

  await page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolA}`).click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/pool/${personalPoolA}`))
  await expect(page.getByTestId('ff-honest-sign-pool-thresholds')).toHaveCount(0)
})
