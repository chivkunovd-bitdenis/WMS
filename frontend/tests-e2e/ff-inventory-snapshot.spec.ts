import { expect, test } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'
import { waitForGetOk, waitForPostOk } from './api-waits'

// TC-NEW-CAT-02 — CAT-02: инвентаризация скрыта до отдельного ТЗ.
// Given: FF admin is logged in; When: they inspect navigation and open /app/ff/inventory directly;
// Then: no inventory menu item is visible and the direct route returns to the product catalog.
// Negative/restriction: the half-ready inventory snapshot screen is not opened from UI routing.
test('ff inventory snapshot route is hidden until a separate product spec', async ({ page }) => {
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
  await expect(page.getByTestId('nav-ff-inventory')).toHaveCount(0)

  await page.goto('/app/ff/inventory')
  await expect(page).toHaveURL(/\/app\/ff\/products/)
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-inventory-snapshot-screen')).toHaveCount(0)
})
