import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-006 — T3.4 (актуализировано 19.08.2026): блока карточек «Требуют
// внимания» больше нет, «Честный знак» у селлера — обычная таблица, как у
// фулфилмента. Товары с низким/нулевым остатком личных кодов маркировки
// находятся через фильтры «На исходе» / «Пустые» в этой же таблице, а не
// через отдельные карточки; «Загрузить КМ» по-прежнему открывает импорт.
test('seller honest sign stock filters surface low and empty stock products in the shared table', async ({
  page,
}) => {
  test.setTimeout(90_000)
  const adminEmail = `e2e-seller-dash-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-seller-dash-sl-${Date.now()}@example.com`
  const password = 'password123'
  const skuLow = `SKU-DASH-LOW-${Date.now()}`
  const skuEmpty = `SKU-DASH-EMPTY-${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller Dash FF')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = String(((await regRes.json()) as { access_token: string }).access_token)
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  const created = await page.request.post('/api/sellers/with-account', {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()
  const sellerId = String(((await created.json()) as { seller_id: string }).seller_id)

  // Товар с низким личным остатком: один загруженный код маркировки (1 <= 10).
  const lowProductRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Low Item',
      sku_code: skuLow,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(lowProductRes.ok()).toBeTruthy()
  const lowProductId = String(((await lowProductRes.json()) as { id: string }).id)

  // Товар с нулевым остатком: требует ЧЗ, но кодов маркировки нет вовсе.
  const emptyProductRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Empty Item',
      sku_code: skuEmpty,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(emptyProductRes.ok()).toBeTruthy()
  const emptyProductId = String(((await emptyProductRes.json()) as { id: string }).id)
  const czPatch = await page.request.patch(
    `${e2eApi}/products/${emptyProductId}/packaging-instructions`,
    {
      headers: auth,
      data: JSON.stringify({ requires_honest_sign: true }),
    },
  )
  expect(czPatch.ok()).toBeTruthy()

  await loginAsSeller(page, sellerEmail, password, { firstTime: false })

  const sellerToken = await page.evaluate(() => localStorage.getItem('wms_token_seller'))
  expect(sellerToken).toBeTruthy()
  const sellerBearer = { Authorization: `Bearer ${sellerToken}` }

  const gtin = '4601234567890'
  const cis = `01${gtin}21${'D'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: sellerBearer,
    multipart: {
      pools_json: JSON.stringify([{ title: 'E2E Dashboard Pool', product_ids: [lowProductId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()

  await page.getByTestId('nav-seller-documents').click()
  await Promise.all([
    waitForGetOk(page, '/api/operations/marking-codes/inventory'),
    page.getByTestId('nav-seller-honest-sign').click(),
  ])
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-seller-dashboard')).toHaveCount(0)

  const lowRow = page.getByTestId(`seller-honest-sign-product-row-${lowProductId}`)
  const emptyRow = page.getByTestId(`seller-honest-sign-product-row-${emptyProductId}`)
  await expect(lowRow).toBeVisible()
  await expect(emptyRow).toBeVisible()

  // Фильтр «На исходе» — только товар с низким личным остатком.
  await page.getByTestId('seller-honest-sign-stock-filter').getByRole('button', { name: 'На исходе' }).click()
  await expect(lowRow).toBeVisible()
  await expect(lowRow).toContainText(skuLow)
  await expect(emptyRow).toHaveCount(0)

  // Фильтр «Пустые» — только товар с нулевым остатком.
  await page.getByTestId('seller-honest-sign-stock-filter').getByRole('button', { name: 'Пустые' }).click()
  await expect(emptyRow).toBeVisible()
  await expect(emptyRow).toContainText(skuEmpty)
  await expect(lowRow).toHaveCount(0)

  // Догрузить коды можно прямо отсюда — карточек «Требуют внимания» больше
  // нет, но действие осталось доступным через общую кнопку «Загрузить КМ».
  await page.getByTestId('seller-honest-sign-open-import').click()
  await expect(page.getByTestId('seller-honest-sign-import-dialog')).toBeVisible()
})
