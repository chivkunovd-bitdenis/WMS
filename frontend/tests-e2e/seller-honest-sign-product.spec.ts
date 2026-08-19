import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-008 — селлер кликает строку товара на «Честный знак» и попадает на карточку
// товара (а не выкидывается перехватом неизвестных путей); порог остатка на карточке —
// только чтение (кнопки «Сохранить» нет); лента внутри карточки — без колонки «Сотрудник»
// (внутренние учётки фулфилмента селлеру не показываем), но с наименованием товара и
// номером документа.
test('seller clicks a product row and reaches the read-only product card with ledger', async ({
  page,
}) => {
  test.setTimeout(90_000)
  const adminEmail = `e2e-seller-hs-prod-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-seller-hs-prod-sl-${Date.now()}@example.com`
  const password = 'password123'
  const sku = `SKU-HS-PROD-${Date.now()}`
  const productName = `HS Card Item ${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Seller HS Product FF')
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
      name: 'HS Product Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()
  const sellerId = String(((await created.json()) as { seller_id: string }).seller_id)

  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name: productName,
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(productRes.ok()).toBeTruthy()
  const productId = String(((await productRes.json()) as { id: string }).id)

  const instructions = await page.request.patch(
    `${e2eApi}/products/${productId}/packaging-instructions`,
    {
      headers: auth,
      data: JSON.stringify({ requires_honest_sign: true }),
    },
  )
  expect(instructions.ok()).toBeTruthy()

  await loginAsSeller(page, sellerEmail, password, { firstTime: false })

  const sellerToken = await page.evaluate(() => localStorage.getItem('wms_token_seller'))
  expect(sellerToken).toBeTruthy()
  const sellerBearer = { Authorization: `Bearer ${sellerToken}` }

  const gtin = '4601234567891'
  const cis = `01${gtin}21${'D'.repeat(20)}0001`
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: sellerBearer,
    multipart: {
      pools_json: JSON.stringify([{ title: 'E2E HS Product Pool', product_ids: [productId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis}`),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()
  const documentNumber = String(((await imp.json()) as { document_number: string }).document_number)

  await page.getByTestId('nav-seller-documents').click()
  await Promise.all([
    waitForGetOk(page, '/api/operations/marking-codes/inventory'),
    page.getByTestId('nav-seller-honest-sign').click(),
  ])
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()

  const row = page.getByTestId(`seller-honest-sign-product-row-${productId}`)
  await expect(row).toBeVisible()

  // Клик по строке ведёт на карточку товара, а не выкидывает с экрана.
  await row.click()
  await expect(page).toHaveURL(new RegExp(`/seller/honest-sign/product/${productId}`))
  await expect(page.getByTestId('seller-honest-sign-product-page')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-product-page')).toContainText(productName)

  // Порог остатка виден, но кнопки «Сохранить» нет — поле только для чтения.
  await expect(page.getByTestId('seller-honest-sign-product-threshold')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-product-threshold-low')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-product-threshold-save')).toHaveCount(0)

  // Лента карточки — без колонки «Сотрудник», но с номером документа импорта.
  await expect(page.getByTestId('seller-honest-sign-product-ledger')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-product-ledger')).not.toContainText('Сотрудник')
  await expect(page.getByTestId('seller-honest-sign-product-ledger')).toContainText(documentNumber)
})
