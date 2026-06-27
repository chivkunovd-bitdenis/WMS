import { test, expect } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-005 — колокольчик: бейдж непрочитанных, клик ведёт по link и помечает прочитанным.
test('FF notifications bell shows badge and navigates on click', async ({ page }) => {
  const adminEmail = `e2e-notify-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Notify')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token).toBeTruthy()

  const seedRes = await page.request.post('/api/operations/notifications/_e2e/seed', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      recipient_type: 'ff_role',
      title: 'E2E тестовое уведомление',
      body: 'Перейти на дашборд',
      link: '/app/ff/dashboard',
    },
  })
  expect(seedRes.ok()).toBeTruthy()
  const notificationId = (await seedRes.json()).id as string

  await page.reload()
  await expect(page.getByTestId('notifications-badge')).toContainText('1')

  await page.getByTestId('notifications-bell').click()
  await expect(page.getByTestId('notifications-menu')).toBeVisible()
  await expect(page.getByTestId(`notification-item-${notificationId}`)).toBeVisible()

  await Promise.all([
    waitForPostOk(page, `/api/operations/notifications/${notificationId}/read`),
    page.getByTestId(`notification-item-${notificationId}`).click(),
  ])

  await expect(page).toHaveURL(/\/app\/ff\/dashboard/)

  const listRes = await page.request.get('/api/operations/notifications', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(listRes.ok()).toBeTruthy()
  expect((await listRes.json()).unread_count).toBe(0)
})
