import { expect, test } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'
import { waitForGetOk, waitForPostOk } from './api-waits'

// Regression: the live storage navigation owns the storage billing route.
// Given: FF admin is logged in; When: they use the storage item or open the route directly;
// Then: the storage screen remains reachable instead of redirecting to the catalog.
test('ff storage route is available from storage navigation', async ({ page }) => {
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
  await expect(page.getByTestId('nav-ff-storage')).toBeVisible()
  await expect(page.getByTestId('nav-ff-storage')).toHaveAttribute('href', '/app/ff/inventory')

  await page.goto('/app/ff/inventory')
  await expect(page).toHaveURL(/\/app\/ff\/inventory/)
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Хранение' })).toBeVisible()
})
