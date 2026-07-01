import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'
import { selectHonestSignSeller } from './ff-honest-sign-helpers'

// TC-NEW-008 — T0.8: диалог импорта, превью по GTIN, загрузка в пул.
test('FF honest sign: import dialog uploads CSV into pool', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-imp-${Date.now()}@example.com`
  const password = 'password123'
  const sku = `SKU-IMP-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Import')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Import Seller', email: `imp-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'E2E Import Item',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(productRes.ok()).toBeTruthy()
  const productId = String(((await productRes.json()) as { id: string }).id)
  const patchRes = await page.request.patch(
    `${e2eApi}/products/${productId}/packaging-instructions`,
    {
      headers: auth,
      data: JSON.stringify({ requires_honest_sign: true }),
    },
  )
  expect(patchRes.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await page.getByTestId('ff-honest-sign-open-import').click()
  await expect(page.getByTestId('ff-honest-sign-import-dialog')).toBeVisible()

  const gtin = '00000000007777'
  const cis = `01${gtin}21${'I'.repeat(20)}0001`
  const previewWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/import/preview') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await Promise.all([
    previewWait,
    page.getByTestId('ff-honest-sign-import-file-input').setInputFiles({
      name: 'demo.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`cis\n${cis}`),
    }),
  ])
  await expect(page.getByTestId(`ff-honest-sign-import-group-${gtin}`)).toBeVisible()

  await page
    .getByTestId(`ff-honest-sign-import-group-${gtin}`)
    .getByRole('textbox', { name: 'Название пула' })
    .fill('UI Import Pool')
  await page
    .getByTestId(`ff-honest-sign-import-product-row-${productId}`)
    .getByRole('checkbox')
    .check()

  const importWait = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/operations/marking-codes/import') &&
      !r.url().includes('/preview') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await Promise.all([importWait, page.getByTestId('ff-honest-sign-import-submit').click()])

  await expect(page.getByTestId('ff-honest-sign-import-toast')).toContainText('Загружено 1')
  const productsTable = page.getByTestId('ff-honest-sign-products-table')
  await expect(productsTable).toContainText(sku)
  await expect(productsTable).toContainText('1')
})

// TC-NEW-008 — негатив: повторная загрузка тех же кодов → дубликаты.
test('FF honest sign: re-import same codes reports duplicates', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-dup-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Dup')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Dup Seller', email: `dup-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000006666'
  const cis = `01${gtin}21${'D'.repeat(20)}0001`
  const bearer = { Authorization: `Bearer ${token}` }
  const first = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Dup Pool', product_ids: [] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(first.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await page.getByTestId('ff-honest-sign-open-import').click()

  const previewWait = page.waitForResponse((r) => r.url().includes('/import/preview') && r.ok())
  await Promise.all([
    previewWait,
    page.getByTestId('ff-honest-sign-import-file-input').setInputFiles({
      name: 'dup.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`cis\n${cis}`),
    }),
  ])
  await expect(page.getByTestId(`ff-honest-sign-import-group-${gtin}`)).toBeVisible()

  const importWait = page.waitForResponse(
    (r) =>
      r.url().includes('/operations/marking-codes/import') &&
      !r.url().includes('/preview') &&
      r.ok(),
  )
  await Promise.all([importWait, page.getByTestId('ff-honest-sign-import-submit').click()])
  await expect(page.getByTestId('ff-honest-sign-import-toast')).toContainText('пропущено')
})
