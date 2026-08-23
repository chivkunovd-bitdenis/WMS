import { test, expect } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'

async function openSettings(page: Parameters<typeof openFulfillmentRegistration>[0]) {
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('nav-ff-settings').click()
}

async function openTariffs(page: Parameters<typeof openFulfillmentRegistration>[0]) {
  await openSettings(page)
  await page.getByTestId('ff-settings-tariffs-tab').click()
}

// S-19-TC-001 — Given an FF administrator, When settings sections are switched, Then the current tab and its existing content are visible.
test('admin switches between settings tabs without losing their existing content', async ({ page }) => {
  await openSettings(page)

  const staffTab = page.getByRole('tab', { name: 'Склад и сотрудники' })
  const tariffsTab = page.getByRole('tab', { name: 'Тарифы ФФ' })

  await expect(staffTab).toHaveAttribute('aria-selected', 'true')
  await expect(tariffsTab).toHaveAttribute('aria-selected', 'false')
  await expect(page.getByTestId('ff-settings-warehouse-panel')).toBeVisible()

  await tariffsTab.click()
  await expect(tariffsTab).toHaveAttribute('aria-selected', 'true')
  await expect(staffTab).toHaveAttribute('aria-selected', 'false')
  await expect(page.getByTestId('ff-settings-tariffs-panel')).toBeVisible()
  await expect(page.getByText('Действующие тарифы')).toBeVisible()

  await staffTab.click()
  await expect(staffTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('ff-settings-warehouse-panel')).toBeVisible()
  await expect(page.getByTestId('ff-settings-users-panel')).toBeVisible()
})

// S-31-TC-002 — Given an FF administrator, When a valid tariff is saved, Then it is visible as the active version.
test('admin creates an active FF tariff', async ({ page }) => {
  await openTariffs(page)
  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('45.5')
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/billing/tariffs') && response.request().method() === 'POST' && response.ok()),
    page.getByRole('button', { name: 'Сохранить ставку' }).click(),
  ])
  await expect.poll(() => page.getByTestId('ff-tariffs-table').textContent()).toContain('45,50\u00a0₽')
})

// S-31-TC-003 — Given an existing tariff, When a later version is saved, Then the new version is active and the old one remains in history.
test('admin creates a later tariff version without replacing history', async ({ page }) => {
  await openTariffs(page)
  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('45.5')
  await page.getByRole('button', { name: 'Сохранить ставку' }).click()
  const tariffsTable = page.getByTestId('ff-tariffs-table')
  await expect.poll(() => tariffsTable.textContent()).toContain('45,50\u00a0₽')

  await page.getByTestId('ff-tariff-new').click()
  await page.getByLabel('Ставка, ₽').fill('50.25')
  await page.getByLabel('Действует с').fill('2099-01-01')
  await page.getByRole('button', { name: 'Сохранить ставку' }).click()
  await expect.poll(() => tariffsTable.textContent()).toContain('50,25\u00a0₽')

  await page.getByTestId('ff-tariff-history-open').click()
  const historyDialog = page.getByRole('dialog', { name: 'История ставок' })
  await expect(historyDialog).toBeVisible()
  const historyText = await historyDialog.textContent()
  expect(historyText).toContain('50,25\u00a0₽')
  expect(historyText).toContain('45,50\u00a0₽')

  await historyDialog.getByTestId('ff-tariff-history-close').click()
  await expect(historyDialog).toBeHidden()
  await expect.poll(() => tariffsTable.textContent()).toContain('50,25\u00a0₽')
})
