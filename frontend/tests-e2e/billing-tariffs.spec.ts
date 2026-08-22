import { test, expect } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'

async function openSettings(page: Parameters<typeof openFulfillmentRegistration>[0]) {
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('nav-ff-settings').click()
  await page.getByTestId('ff-settings-tariffs-tab').click()
}

// S-31-TC-002 — Given an FF administrator, When a valid tariff is saved, Then it is visible as the active version.
test('admin creates an active FF tariff', async ({ page }) => {
  await openSettings(page)
  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('45')
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/billing/tariffs') && response.request().method() === 'POST' && response.ok()),
    page.getByRole('button', { name: 'Сохранить ставку' }).click(),
  ])
  await expect(page.getByTestId('ff-tariffs-table')).toContainText('45,00 ₽')
})

// S-31-TC-003 — Given an existing tariff, When a later version is saved, Then the new version is active and the old one remains in history.
test('admin creates a later tariff version without replacing history', async ({ page }) => {
  await openSettings(page)
  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('45')
  await page.getByRole('button', { name: 'Сохранить ставку' }).click()
  await expect(page.getByTestId('ff-tariffs-table')).toContainText('45,00 ₽')

  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('50')
  await page.getByLabel('Действует с').fill('2099-01-01')
  await page.getByRole('button', { name: 'Сохранить ставку' }).click()
  await expect(page.getByTestId('ff-tariffs-table')).toContainText('50,00 ₽')
  await page.getByTitle('Открыть историю ставок').click()
  await expect(page.getByTestId('ff-tariff-history')).toContainText('45,00 ₽')
})

