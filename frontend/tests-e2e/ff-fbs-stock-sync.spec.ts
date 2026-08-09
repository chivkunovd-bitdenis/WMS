import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk, waitForPutOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

async function registerFf(page: import('@playwright/test').Page, tag: string) {
  const email = `e2e-fbs-stock-${tag}-${Date.now()}@example.com`
  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`E2E FBS Stock ${tag}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  await expect(page.getByTestId('dashboard')).toBeVisible()
}

// TC-NEW-FBS-STOCK-UI-001 — привязка WB↔WMS, ручная синхронизация и статус (реальный backend).
// Given: оператор ФФ, селлер и склад WMS; When: создаёт привязку, запускает sync, открывает статус;
// Then: привязка в списке, feedback по sync виден, панель статуса открывается без mock API.
test('fbs stock sync: bind, manual sync, status panel', async ({ page }) => {
  await registerFf(page, 'ui')

  const token = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${token}` }

  const seller = (await (
    await page.request.post('/api/sellers', { headers: h, data: { name: 'Селлер Stock' } })
  ).json()) as { id: string }

  const whCode = `wh-stock-${Date.now()}`
  const wh = (await (
    await page.request.post('/api/warehouses', {
      headers: h,
      data: { name: 'Склад FBS', code: whCode },
    })
  ).json()) as { id: string; name: string }

  await page.goto('/app/ff/fbs/stock-sync')
  await expect(page.getByTestId('fbs-stock-sync-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-nav-stock-sync')).toBeVisible()

  await page.getByTestId('fbs-stock-seller-filter').click()
  await page.getByRole('option', { name: 'Селлер Stock' }).click()

  await page.getByTestId('fbs-stock-add-binding').click()
  await page.getByTestId('fbs-stock-add-wb-id').fill('501001')
  await page.getByTestId('fbs-stock-add-wms-select').click()
  await page.getByRole('option', { name: new RegExp(wh.name) }).click()

  await Promise.all([
    waitForPutOk(page, '/warehouse-bindings/501001'),
    waitForGetOk(page, '/warehouse-bindings'),
    page.getByTestId('fbs-stock-add-save').click(),
  ])

  await expect(page.getByTestId('fbs-stock-binding-row')).toHaveCount(1)
  await expect(page.getByTestId('fbs-stock-binding-row')).toContainText('501001')

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/stocks/sync') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('fbs-stock-sync-all').click(),
  ])
  await expect(page.getByTestId('fbs-stock-sync-feedback')).toBeVisible()

  await Promise.all([
    waitForGetOk(page, '/stocks/sync-status'),
    page.getByTestId('fbs-stock-status-btn').click(),
  ])
  await expect(page.getByTestId('fbs-stock-status-panel')).toBeVisible()

  // Disable binding — real DELETE
  await page.getByRole('button', { name: 'Закрыть' }).click()
  await page.getByTestId('fbs-stock-disable-binding').click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes('/warehouse-bindings/501001') &&
        r.status() === 200,
    ),
    waitForGetOk(page, '/warehouse-bindings'),
    page.getByRole('dialog', { name: 'Отключить связь складов?' }).getByRole('button', { name: 'Отключить' }).click(),
  ])
  await expect(page.getByTestId('fbs-stock-bindings-empty')).toBeVisible()

  // Seller id used for binding API path
  expect(seller.id).toBeTruthy()
  expect(wh.id).toBeTruthy()
})
