import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits'
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow'

// TC-NEW-007 — T4.1: настройки кредов ЧЗ в кабинете селлера (без утечки секретов в UI).
test('seller can save marking credentials settings from settings page', async ({ page }) => {
  const adminEmail = `e2e-cz-cred-adm-${Date.now()}@example.com`
  const sellerEmail = `e2e-cz-cred-sl-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E CZ Cred FF')
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
      name: 'CZ Cred Seller',
      email: sellerEmail,
      password,
    }),
  })
  expect(created.ok()).toBeTruthy()

  await loginAsSeller(page, sellerEmail, password, { firstTime: false })

  await Promise.all([
    waitForGetOk(page, '/api/operations/marking-codes/self/credentials'),
    page.getByTestId('nav-seller-settings').click(),
  ])
  await expect(page.getByTestId('seller-settings-marking-card')).toBeVisible()
  await expect(page.getByTestId('seller-settings-cz-signing')).toContainText('Вручную')

  await page.getByTestId('seller-settings-cz-edit').click()
  await expect(page.getByTestId('seller-settings-cz-dialog')).toBeVisible()

  await page.getByTestId('seller-settings-cz-signing-select').click()
  await page.getByRole('option', { name: 'КЭП фулфилмента + МЧД' }).click()
  await page.getByTestId('seller-settings-cz-mchd-id').fill('MCHD-E2E-1')
  await page.getByTestId('seller-settings-cz-token').fill('e2e-cz-secret-token')
  await page.getByTestId('seller-settings-cz-auto-introduce').click()

  const [patchRes] = await Promise.all([
    waitForPatchOk(page, '/api/operations/marking-codes/self/credentials'),
    page.getByTestId('seller-settings-cz-save').click(),
  ])
  expect(patchRes.ok()).toBeTruthy()
  const patchBody = (await patchRes.json()) as { has_cz_token: boolean; signing_method: string }
  expect(patchBody.has_cz_token).toBe(true)
  expect(patchBody.signing_method).toBe('ff_kep_mchd')
  expect(JSON.stringify(patchBody)).not.toContain('e2e-cz-secret')

  await expect(page.getByTestId('seller-settings-ok')).toContainText('сохранены')
  await expect(page.getByTestId('seller-settings-cz-signing')).toContainText('КЭП фулфилмента')
  await expect(page.getByTestId('seller-settings-cz-tokens')).toContainText('ЧЗ ✓')
  await expect(page.getByTestId('seller-settings-cz-auto')).toContainText('вкл')
})
