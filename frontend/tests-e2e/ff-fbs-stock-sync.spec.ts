import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
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

// TC-NEW-FBS-STOCK-UI-001 — настройка FBS-остатка остаётся в каталоге.
// Given: FF-admin, два реальных WMS-склада и обслуживаемые/необслуживаемые WB-направления;
// When: открывает старый URL и меняет сопоставление в существующем dialog каталога;
// Then: URL редиректит в каталог, PUT получает WB id + выбранный WMS id;
// negative: старая вкладка отсутствует, served=false направление не участвует в долях само.
test('old FBS stock route redirects to catalog and catalog warehouse binding works', async ({ page }) => {
  await registerFf(page, 'catalog-bind')

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

  const warehouseA = (await (
    await page.request.post('/api/warehouses', {
      headers: h,
      data: { name: 'Склад FBS A', code: `wh-stock-a-${Date.now()}` },
    })
  ).json()) as { id: string; name: string }
  const warehouseB = (await (
    await page.request.post('/api/warehouses', {
      headers: h,
      data: { name: 'Склад FBS B', code: `wh-stock-b-${Date.now()}` },
    })
  ).json()) as { id: string; name: string }

  const product = (await (
    await page.request.post('/api/products', {
      headers: h,
      data: {
        name: 'Товар FBS-сопоставления',
        sku_code: `SKU-FBS-BIND-${Date.now()}`,
        length_mm: 10,
        width_mm: 10,
        height_mm: 10,
        seller_id: seller.id,
      },
    })
  ).json()) as { id: string }

  const configure = await page.request.put(
    `/api/fbs-sellers/${seller.id}/warehouses/501001`,
    {
      headers: h,
      data: { served: true, wms_warehouse_id: warehouseA.id },
    },
  )
  expect(configure.ok()).toBeTruthy()

  // Необслуживаемое направление должно быть доступно только для явного
  // сопоставления: до выбора WMS-склада оно не участвует в долях остатка.
  await page.route(
    `**/api/operations/fbs-sellers/${seller.id}/warehouses`,
    async (route) => {
      const response = await route.fetch()
      const rows = (await response.json()) as Array<Record<string, unknown>>
      await route.fulfill({
        response,
        json: [
          ...rows,
          {
            id: 501003,
            wb_warehouse_id: 501003,
            name: 'E2E Unserved WB',
            served: false,
            wms_warehouse_id: null,
          },
        ],
      })
    },
  )

  // App перечитывает созданные склады и селлера после перезагрузки.
  await page.reload()
  await page.goto('/app/ff/fbs/stock-sync')
  await expect(page).toHaveURL(/\/app\/ff\/products$/)
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('fbs-stock-sync-screen')).toHaveCount(0)
  await expect(page.getByTestId('fbs-nav-stock-sync')).toHaveCount(0)

  await page.getByTestId(`ff-catalog-fbs-row-${product.id}`).click()
  await expect(page.getByTestId('fbs-stock-dialog')).toBeVisible()
  await expect(page.getByTestId('fbs-stock-bind-501003')).toBeVisible()
  await expect(page.getByTestId('fbs-stock-percent-501003')).toHaveCount(0)

  const bindingSelect = page.getByTestId('fbs-stock-bind-501003')
  await expect(bindingSelect.locator('option')).toHaveText([
    'не сопоставлен',
    warehouseA.name,
    warehouseB.name,
  ])

  const [bindingRequest] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PUT' &&
        request.url().includes(`/api/fbs-sellers/${seller.id}/warehouses/501003`),
    ),
    bindingSelect.selectOption(warehouseB.id),
  ])
  expect(bindingRequest.postDataJSON()).toEqual({
    served: true,
    wms_warehouse_id: warehouseB.id,
  })
  await expect(bindingSelect).toHaveValue(warehouseB.id)
  await expect(page.getByTestId('fbs-stock-percent-501003')).toBeVisible()

  // TC-NEW-FBS-STOCK-UI-002 — галочка «обслуживаем склад» выключает направление.
  // Given: направление 501003 сопоставлено и обслуживается;
  // When: оператор снимает галочку в той же модалке;
  // Then: уходит PUT со served=false и сохранённым складом, ползунок доли пропадает;
  // negative/ограничение: у выключенного направления выпадашка склада заперта, чтобы
  // выбор склада не включил его обратно молча; повторная галочка возвращает ползунок.
  const servedToggle = page.getByTestId('fbs-stock-served-501003')
  await expect(servedToggle).toBeChecked()

  const [unservedRequest] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PUT' &&
        request.url().includes(`/api/fbs-sellers/${seller.id}/warehouses/501003`),
    ),
    // Галка управляемая: состояние меняется только после ответа сервера,
    // поэтому click, а не uncheck — тот требует смены состояния сразу.
    servedToggle.click(),
  ])
  await expect(servedToggle).not.toBeChecked()
  expect(unservedRequest.postDataJSON()).toEqual({
    served: false,
    wms_warehouse_id: warehouseB.id,
  })

  await expect(page.getByTestId('fbs-stock-percent-501003')).toHaveCount(0)
  await expect(bindingSelect).toBeDisabled()

  const [servedAgainRequest] = await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === 'PUT' &&
        request.url().includes(`/api/fbs-sellers/${seller.id}/warehouses/501003`),
    ),
    servedToggle.click(),
  ])
  await expect(servedToggle).toBeChecked()
  expect(servedAgainRequest.postDataJSON()).toEqual({
    served: true,
    wms_warehouse_id: warehouseB.id,
  })
  await expect(page.getByTestId('fbs-stock-percent-501003')).toBeVisible()
})
