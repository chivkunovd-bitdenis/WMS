import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-006 — T3.4: дашборд остатков селлера, кнопка «Догрузить» открывает импорт.
test('seller honest sign dashboard shows pool card and upload opens import', async ({ page }) => {
  const adminEmail = `e2e-seller-dash-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-seller-dash-sl-${Date.now()}@example.com`
  const password = 'password123'

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

  const created = await page.request.post('/api/sellers/with-account', {
    headers: auth,
    data: JSON.stringify({
      name: 'Dash Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()

  await loginAsSeller(page, sellerEmail, password, { firstTime: false })

  await page.getByTestId('nav-seller-honest-sign').click()
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()

  const sellerToken = await page.evaluate(() => localStorage.getItem('wms_token_seller'))
  expect(sellerToken).toBeTruthy()

  const poolRes = await page.request.post('/api/operations/marking-codes/_e2e/pools', {
    headers: { Authorization: `Bearer ${sellerToken}` },
    data: { gtin: '4601234567890', title: 'E2E Dashboard Pool' },
  })
  expect(poolRes.ok()).toBeTruthy()
  const poolId = (await poolRes.json()).pool_id as string

  await page.getByTestId('nav-seller-documents').click()
  await Promise.all([
    waitForGetOk(page, '/api/operations/marking-codes/pools'),
    page.getByTestId('nav-seller-honest-sign').click(),
  ])
  await expect(page.getByTestId('seller-honest-sign-page')).toBeVisible()
  await expect(page.getByTestId('seller-honest-sign-seller-dashboard')).toBeVisible()
  const card = page.getByTestId(`seller-honest-sign-pool-card-${poolId}`)
  await expect(card).toBeVisible()
  await expect(card).toContainText('E2E Dashboard Pool')

  await card.getByTestId(`seller-honest-sign-pool-card-upload-${poolId}`).click()
  await expect(page.getByTestId('seller-honest-sign-import-dialog')).toBeVisible()
})
