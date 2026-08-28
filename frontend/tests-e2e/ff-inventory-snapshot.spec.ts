import { expect, test } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'
import { waitForGetOk, waitForPostOk } from './api-waits'

// TC-S11-001 — FF admin открывает действующий экран расчёта хранения.
// Given: FF admin is logged in; When: they inspect navigation and open /app/ff/inventory directly;
// Then: the storage screen is visible and the obsolete snapshot prototype is not routed.
test('ff inventory route opens the storage calculation screen', async ({ page }) => {
  const email = `e2e-ff-inventory-hidden-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Inventory Hidden')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await expect(page.getByTestId('dashboard')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Хранение', exact: true })).toBeVisible()

  await page.goto('/app/ff/inventory')
  await expect(page).toHaveURL(/\/app\/ff\/inventory/)
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await expect(page.getByTestId('ff-inventory-snapshot-screen')).toHaveCount(0)
})
