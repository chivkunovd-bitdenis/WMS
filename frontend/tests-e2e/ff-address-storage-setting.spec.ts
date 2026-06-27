import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-MP-001 — TASK-001: админ переключает «Адресное хранение», значение сохраняется в /auth/me.
// REV-FIX-004 / TC-S03: при выключении виден info о переносе остатков на зону сортировки.
test('admin toggles address storage setting and me reflects change', async ({ page }) => {
  const adminEmail = `e2e-address-storage-${Date.now()}@example.com`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Address Storage')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await page.getByTestId('nav-ff-settings').click()
  await expect(page.getByTestId('ff-settings-warehouse-panel')).toBeVisible()
  const checkbox = page.getByRole('checkbox', { name: /Адресное хранение включено/i })
  await expect(checkbox).toBeChecked()

  const patchOff = waitForPatchOk(page, '/api/tenant/settings')
  const meOff = waitForGetOk(page, '/api/auth/me')
  await checkbox.uncheck()
  await patchOff
  await meOff
  await expect(page.getByTestId('ff-settings-address-storage-migration-info')).toContainText(
    'перенесены на зону сортировки',
  )
  await expect(checkbox).not.toBeChecked()

  const patchOn = waitForPatchOk(page, '/api/tenant/settings')
  const meOn = waitForGetOk(page, '/api/auth/me')
  await checkbox.check()
  await patchOn
  await meOn
  await expect(page.getByTestId('ff-settings-address-storage-saved')).toContainText('включено')
  await expect(checkbox).toBeChecked()
})
