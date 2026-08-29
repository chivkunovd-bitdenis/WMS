import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-212 — на карточке отгрузки имя склада маркетплейса стоит рядом с чипом площадки,
// а не вместо него: оператор должен видеть, куда именно едет поставка.
test('S-12 keeps warehouse name beside the marketplace chip', async ({ page }) => {
  const suffix = String(Date.now())
  const warehouseName = `Склад Ozon ${suffix}`
  const email = `e2e-s12-chip-${suffix}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E S-12 chip')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token).toBeTruthy()
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const warehouseResponse = await page.request.post(`${e2eApi}/warehouses`, {
    headers,
    data: JSON.stringify({ name: warehouseName, code: `s12-${suffix}` }),
  })
  expect(warehouseResponse.ok(), await warehouseResponse.text()).toBeTruthy()
  const warehouseId = String(((await warehouseResponse.json()) as { id: string }).id)
  const sellerResponse = await page.request.post(`${e2eApi}/sellers`, {
    headers,
    data: JSON.stringify({ name: `S-12 seller ${suffix}` }),
  })
  expect(sellerResponse.ok(), await sellerResponse.text()).toBeTruthy()
  const sellerId = String(((await sellerResponse.json()) as { id: string }).id)
  const unloadResponse = await page.request.post(
    `${e2eApi}/operations/marketplace-unload-requests`,
    {
      headers,
      data: JSON.stringify({
        warehouse_id: warehouseId,
        seller_id: sellerId,
        marketplace: 'ozon',
      }),
    },
  )
  expect(unloadResponse.ok(), await unloadResponse.text()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-mp-shipments').click()
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()
  const row = page.locator('[data-doc-kind="marketplace_unload"]').filter({ hasText: warehouseName })
  await expect(row).toBeVisible()
  await expect(row).toContainText(warehouseName)
  await expect(row.getByTestId('ff-mp-marketplace-chip')).toHaveText('Ozon')
  await page.screenshot({
    path: '../docs/evidence/ozon-integration-20260825/S-12/live-browser-corrected.png',
    fullPage: true,
  })
})
