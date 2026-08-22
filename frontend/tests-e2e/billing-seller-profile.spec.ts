import { test, expect } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'

// S-31-TC-001 — Given an administrator has a seller, When valid billing details are saved, Then confirmation is visible.
test('admin saves seller billing profile in seller dialog', async ({ page }) => {
  const stamp = Date.now()
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`Billing ${stamp}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(`billing-${stamp}@example.com`)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click()
  await page.getByTestId('nav-sellers').click()
  await page.getByTestId('seller-name').fill(`Seller ${stamp}`)
  await page.getByTestId('seller-email').fill(`seller-${stamp}@example.com`)
  await page.getByTestId('seller-submit').click()
  await page.getByTestId('seller-row').click()
  await page.getByText('Реквизиты для счетов').click()
  await page.getByTestId('seller-legal-name').fill('ООО «Луна»')
  await page.getByTestId('seller-inn').fill('7707083893')
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/billing/profiles/sellers/') && response.request().method() === 'PUT' && response.ok()),
    page.getByTestId('seller-profile-save').click(),
  ])
  await expect(page.getByTestId('seller-profile-success')).toHaveText('Реквизиты сохранены')
})

// S-31-TC-009 — Given saved details exist, When an invalid INN is submitted, Then the readable error is shown and the saved values remain.
test('invalid seller INN leaves previously saved profile intact', async ({ page }) => {
  const stamp = Date.now()
  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`Billing negative ${stamp}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(`billing-negative-${stamp}@example.com`)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click()
  await page.getByTestId('nav-sellers').click()
  await page.getByTestId('seller-name').fill(`Seller negative ${stamp}`)
  await page.getByTestId('seller-email').fill(`seller-negative-${stamp}@example.com`)
  await page.getByTestId('seller-submit').click()
  await page.getByTestId('seller-row').click()
  await page.getByText('Реквизиты для счетов').click()

  const legalName = 'ООО «Луна Негатив»'
  const kpp = '770701001'
  await page.getByTestId('seller-legal-name').fill(legalName)
  await page.getByTestId('seller-inn').fill('7707083893')
  await page.getByTestId('seller-kpp').fill(kpp)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/billing/profiles/sellers/') && response.request().method() === 'PUT' && response.ok()),
    page.getByTestId('seller-profile-save').click(),
  ])

  await page.getByTestId('seller-inn').fill('7707083894')
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/billing/profiles/sellers/') && response.request().method() === 'PUT' && !response.ok()),
    page.getByTestId('seller-profile-save').click(),
  ])
  await expect(page.getByTestId('seller-profile-error')).toContainText('контрольное число не совпадает')
  await expect(page.getByTestId('seller-profile-success')).toHaveText('Реквизиты сохранены')
  await expect(page.getByTestId('seller-legal-name')).toHaveValue(legalName)
  await expect(page.getByTestId('seller-inn')).toHaveValue('7707083894')
  await expect(page.getByTestId('seller-kpp')).toHaveValue(kpp)
})
