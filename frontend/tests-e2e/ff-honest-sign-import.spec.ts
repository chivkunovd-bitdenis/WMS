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
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`
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
  const productSearch = page
    .getByTestId(`ff-honest-sign-import-group-${gtin}`)
    .getByRole('textbox', { name: 'Поиск товаров' })
  await productSearch.fill('not-found')
  await expect(page.getByTestId(`ff-honest-sign-import-products-empty-${gtin}`)).toContainText(
    'По поиску товары не найдены',
  )
  await productSearch.fill('')

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

// TC-NEW-008 — регрессия: reset прерванного превью снимает занятость диалога.
test('FF honest sign: reset after aborted preview re-enables import dialog actions', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-abort-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Preview Abort')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const sellerARes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E Abort Seller A', email: `abort-a-${Date.now()}@example.com` }),
  })
  const sellerAId = String(((await sellerARes.json()) as { id: string }).id)

  let releasePreview: (() => void) | null = null
  let previewCalls = 0
  await page.route('**/operations/marking-codes/import/preview', async (route) => {
    previewCalls += 1
    if (previewCalls === 1) {
      await new Promise<void>((resolve) => {
        releasePreview = resolve
      })
      await route.abort('aborted').catch(() => undefined)
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        groups: [{ gtin: '00000000005556', codes_count: 1, suggested_title: 'GTIN ...5556' }],
        total_codes: 1,
        invalid_count: 0,
        duplicates_in_file: 0,
      }),
    })
  })

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerAId)
  await page.getByTestId('ff-honest-sign-open-import').click()
  await expect(page.getByTestId('ff-honest-sign-import-dialog')).toBeVisible()

  const gtin = '00000000005555'
  const cis = `01${gtin}21${'A'.repeat(20)}0001`
  await page.getByTestId('ff-honest-sign-import-file-input').setInputFiles({
    name: 'abort.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(`cis\n${cis}`),
  })
  await expect(page.getByTestId('ff-honest-sign-import-parsing')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-import-submit')).toBeDisabled()

  releasePreview?.()

  await expect(page.getByTestId('ff-honest-sign-import-parsing')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Отмена' })).toBeEnabled()
  await expect(page.getByTestId('ff-honest-sign-import-submit')).toBeDisabled()

  const nextGtin = '00000000005556'
  const nextCis = `01${nextGtin}21${'B'.repeat(20)}0001`
  await page.getByTestId('ff-honest-sign-import-file-input').setInputFiles({
    name: 'after-reset.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(`cis\n${nextCis}`),
  })
  await expect(page.getByTestId(`ff-honest-sign-import-group-${nextGtin}`)).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-import-submit')).toBeEnabled()
})

// TC-NEW-008 — негатив: у селлера есть товары, но нет признака ЧЗ.
test('FF honest sign: import dialog explains when seller has no honest-sign products', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-no-cz-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E No CZ Products')
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
    data: JSON.stringify({ name: 'E2E No CZ Seller', email: `no-cz-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)
  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Regular Item',
      sku_code: `SKU-NO-CZ-${Date.now()}`,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(productRes.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await page.getByTestId('ff-honest-sign-open-import').click()

  const gtin = '00000000004444'
  const cis = `01${gtin}21${'N'.repeat(20)}0001`
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/import/preview') && r.ok()),
    page.getByTestId('ff-honest-sign-import-file-input').setInputFiles({
      name: 'no-cz.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(`cis\n${cis}`),
    }),
  ])
  await expect(page.getByTestId(`ff-honest-sign-import-products-empty-${gtin}`)).toContainText(
    'нет товаров с признаком «Нужен Честный знак при упаковке»',
  )
  await expect(page.getByTestId(`ff-honest-sign-import-products-empty-${gtin}`)).toContainText(
    'каталог товаров → товар → упаковка и маркировка',
  )
})

// TC-NEW-008 — непривязанные КМ видны и ведут к привязке пула.
test('FF honest sign: unlinked available pool is visible and opens product linking', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-unlinked-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Unlinked Pool')
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
    data: JSON.stringify({ name: 'E2E Unlinked Seller', email: `unlinked-${Date.now()}@example.com` }),
  })
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)

  const gtin = '00000000003333'
  const cis = `01${gtin}21${'U'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'Unlinked Pool', product_ids: [] }]),
      files: {
        name: 'unlinked.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()
  const poolId = String(((await imp.json()) as { pools: { pool_id: string }[] }).pools[0].pool_id)

  await page.getByTestId('nav-ff-honest-sign').click()
  await selectHonestSignSeller(page, sellerId)
  await expect(page.getByTestId('ff-honest-sign-unlinked-hint')).toContainText('Кодов без привязки к товару: 1')
  await expect(page.getByTestId('ff-honest-sign-products-table')).toContainText('есть КМ без привязки')
  await expect(page.getByTestId(`ff-honest-sign-unlinked-pool-row-${poolId}`)).toContainText('Unlinked Pool')
  await page.getByTestId(`ff-honest-sign-unlinked-pool-link-${poolId}`).click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/pool/${poolId}\\?tab=products`))
  await expect(page.getByTestId('ff-honest-sign-pool-products')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-pool-products-empty')).toContainText('Товары не привязаны')
  await expect(page.getByTestId('ff-honest-sign-pool-link-products')).toBeVisible()
})

// TC-NEW-008 — негатив: повторная загрузка тех же кодов → дубликаты.
test('FF honest sign: re-import same codes reports duplicates', async ({ page }) => {
  test.setTimeout(90_000)
  const email = `e2e-dup-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

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
