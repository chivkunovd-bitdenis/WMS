import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-004 — право shift_lead: пункт «Перепечатки» и API очереди.
test('shift_lead permission shows reprints nav and grants queue API', async ({ page }) => {
  const adminEmail = `e2e-shift-admin-${Date.now()}@example.com`
  const staffEmail = `e2e-shift-staff-${Date.now()}@example.com`
  const staffPassword = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Shift Lead')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(staffPassword)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await expect(page.getByTestId('nav-ff-honest-sign-reprints')).toBeVisible()

  await page.getByTestId('nav-ff-settings').click()
  await page.getByTestId('ff-staff-email').fill(staffEmail)
  await Promise.all([
    waitForPostOk(page, '/api/auth/staff-accounts'),
    waitForGetOk(page, '/api/auth/staff-accounts'),
    page.getByTestId('ff-staff-submit').click(),
  ])
  const staffRow = page.getByTestId('ff-staff-row').filter({ hasText: staffEmail })
  const staffId = await staffRow.getAttribute('data-staff-id')
  expect(staffId).toBeTruthy()

  await page.getByTestId('logout').click()
  await page.getByTestId('login-form').getByLabel('Email').fill(staffEmail)
  await page.getByTestId('login-form').getByLabel('Пароль').fill('')
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/login') && (r.status() === 200 || r.status() === 403)),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])
  await page.getByTestId('seller-password-setup-form').getByLabel('Новый пароль').fill(staffPassword)
  await page.getByTestId('seller-password-setup-form').getByLabel('Повтор пароля').fill(staffPassword)
  await Promise.all([
    waitForPostOk(page, '/api/auth/set-initial-password'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('seller-password-setup-submit').click(),
  ])

  await expect(page.getByTestId('nav-ff-honest-sign-reprints')).toHaveCount(0)

  await page.getByTestId('logout').click()
  await page.getByTestId('login-form').getByLabel('Email').fill(adminEmail)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(staffPassword)
  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])

  await page.getByTestId('nav-ff-settings').click()
  const staffRowAfter = page.getByTestId('ff-staff-row').filter({ hasText: staffEmail })
  await Promise.all([
    waitForPatchOk(page, `/api/auth/staff-accounts/${staffId}/permissions`),
    staffRowAfter.getByTestId(`ff-staff-perm-${staffId}-shift_lead`).click(),
  ])

  await page.getByTestId('logout').click()
  await page.getByTestId('login-form').getByLabel('Email').fill(staffEmail)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(staffPassword)
  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])

  await expect(page.getByTestId('nav-ff-honest-sign-reprints')).toBeVisible()
  await page.getByTestId('nav-ff-honest-sign-reprints').click()
  await expect(page).toHaveURL(/\/app\/ff\/honest-sign\/reprints/)
  await expect(page.getByTestId('ff-honest-sign-reprints-page')).toBeVisible()
  await expect(page.getByTestId('ff-honest-sign-reprints-page-empty')).toBeVisible()
})
