import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { selectHonestSignSeller } from './ff-honest-sign-helpers'

// TC-NEW-007 — product-first vitrine: товар в списке, привязка через API, переход в карточку пула.
test('FF honest sign: product list row, link product via API, open pool card', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-pools-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-PL-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Pools')
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
    data: JSON.stringify({ name: 'E2E Pools Seller', email: `pl-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const prRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Pool Item',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  const productId = String(((await prRes.json()) as { id: string }).id)

  const gtin = '00000000008888'
  const cis = `01${gtin}21${'G'.repeat(20)}0001`
  const poolRes = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E List Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(poolRes.ok()).toBeTruthy()
  const poolId = String(((await poolRes.json()) as { pools: { pool_id: string }[] }).pools[0].pool_id)

  const linkRes = await page.request.put(
    `${e2eApi}/operations/marking-codes/pools/${poolId}/products`,
    {
      headers: { ...auth, 'Content-Type': 'application/json' },
      data: JSON.stringify({ product_ids: [productId] }),
    },
  )
  expect(linkRes.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  const productRow = page.getByTestId(`ff-honest-sign-product-row-${productId}`)
  await expect(productRow).toBeVisible()
  await expect(productRow).toContainText(sku)
  await expect(productRow).toContainText('1')

  // TC-NEW-POOLS-02 — KPI: static vs interactive cards, filter toggle, ledger link
  await expect(page.getByTestId('ff-honest-sign-kpi-spend-7d')).toHaveAttribute('data-interactive', 'false')
  await page.getByTestId('ff-honest-sign-kpi-low-stock').click()
  await expect(page.getByTestId('ff-honest-sign-stock-filter').getByRole('button', { name: 'На исходе' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByTestId('ff-honest-sign-kpi-available').click()
  await expect(page.getByTestId('ff-honest-sign-stock-filter').getByRole('button', { name: 'Все' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByTestId('ff-honest-sign-kpi-defective').click()
  await expect(page).toHaveURL(/\/app\/ff\/honest-sign\/ledger\?event_type=defective/)
  await expect(page.getByTestId('ff-honest-sign-ledger-event-type').locator('input')).toHaveValue('defective')
  await page.getByTestId('ff-honest-sign-ledger-back').click()
  await selectHonestSignSeller(page, sellerId)

  await productRow.click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/product/${productId}`))
  await expect(page.getByTestId('ff-honest-sign-product-page')).toBeVisible()
  await page.getByTestId(`ff-honest-sign-product-personal-pool-${poolId}`).click()
  await expect(page.getByTestId('ff-honest-sign-pool-page')).toBeVisible()
})
