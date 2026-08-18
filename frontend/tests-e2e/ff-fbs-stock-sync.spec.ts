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

// TC-NEW-FBS-STOCK-UI-001 — привязка реального WB-склада из строки к WMS-складу.
// Given: оператор ФФ, селлер с WB-токеном и физический WMS-склад;
// When: открывает склады селлера, выбирает WMS-склад в строке WB-склада и включает публикацию;
// Then: ручного ввода WB ID нет, связь видна в строке, sync/status работают по выбранному складу.
test('fbs seller warehouses: row binding, manual sync, status panel', async ({ page }) => {
  await registerFf(page, 'ui')

  const token = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${token}` }

  const seller = (await (
    await page.request.post('/api/sellers', { headers: h, data: { name: 'Селлер Stock' } })
  ).json()) as { id: string }
  const tokenPatch = await page.request.patch(
    `/api/integrations/wildberries/sellers/${seller.id}/tokens`,
    {
      headers: h,
      data: { marketplace_api_token: 'wb-marketplace-token' },
    },
  )
  expect(tokenPatch.ok()).toBeTruthy()

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

  const row = page.getByTestId('fbs-stock-binding-row').first()
  await expect(row).toContainText('E2E Seller Warehouse')
  await expect(row).toContainText('Moscow')
  await expect(row).toContainText('WB ID 501001')
  await expect(page.getByTestId('fbs-stock-add-binding')).toHaveCount(0)

  await row.getByTestId('fbs-stock-row-wms-select').click()
  await Promise.all([
    waitForPutOk(page, '/warehouse-bindings/501001'),
    waitForGetOk(page, '/warehouse-bindings'),
    page.getByRole('option', { name: new RegExp(wh.name) }).click(),
  ])

  await expect(row).toContainText('готов к публикации')
  await Promise.all([
    waitForPutOk(page, '/warehouse-bindings/501001'),
    waitForGetOk(page, '/warehouse-bindings'),
    row.getByTestId('fbs-stock-sync-toggle').click(),
  ])
  await expect(row).toContainText('публикация включена')

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

  await row.getByTestId('fbs-stock-row-menu-btn').click()
  await Promise.all([
    waitForGetOk(page, '/stocks/sync-status'),
    page.getByTestId('fbs-stock-status-btn').click(),
  ])
  await expect(page.getByTestId('fbs-stock-status-panel')).toBeVisible()

  // Disable binding — real DELETE
  await page.getByRole('button', { name: 'Закрыть' }).click()
  await row.getByTestId('fbs-stock-row-menu-btn').click()
  await page.getByTestId('fbs-stock-disable-binding').click()
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        r.url().includes('/warehouse-bindings/501001') &&
        r.status() === 200,
    ),
    waitForGetOk(page, '/warehouse-bindings'),
    page.getByRole('dialog', { name: 'Отключить сопоставление складов?' }).getByRole('button', { name: 'Отключить' }).click(),
  ])
  await expect(row).toContainText('склад не сопоставлен')

  // Seller id used for binding API path
  expect(seller.id).toBeTruthy()
  expect(wh.id).toBeTruthy()
})
