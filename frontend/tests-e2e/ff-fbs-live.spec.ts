import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'

const emuUrl = process.env.E2E_LIVE_EMULATOR_URL ?? 'http://127.0.0.1:19081'
const emuAdminToken = process.env.E2E_LIVE_EMULATOR_ADMIN_TOKEN ?? 'fbs-live-local-admin'
const wbToken = process.env.E2E_LIVE_WB_TOKEN ?? 'fbs-live-token'
const wbSellerKey = process.env.E2E_LIVE_WB_SELLER_KEY ?? 'fbs_live_seller'
const wbWarehouseId = 501001
const wbBarcode = '2000000000011'
const wbChrtId = 111001

type Created = { id: string }

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

async function expectJson<T>(response: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> {
  expect(response.ok(), `${response.status()} ${await response.text()}`).toBeTruthy()
  return await response.json() as T
}

async function registerFf(page: Page): Promise<string> {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`
  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill(`Live FBS ${suffix}`)
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(`live-fbs-${suffix}@example.com`)
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123')
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(page.getByTestId('dashboard')).toBeVisible()
  return await page.evaluate(() => localStorage.getItem('wms_token_ff') ?? '')
}

async function waitForJob(request: APIRequestContext, token: string, id: string): Promise<void> {
  await expect.poll(async () => {
    const response = await request.get(`/api/operations/background-jobs/${id}`, { headers: authHeaders(token) })
    const body = await expectJson<{ status: string; error_message: string | null }>(response)
    if (body.status === 'failed') throw new Error(body.error_message ?? 'FBS order sync failed')
    return body.status
  }, { timeout: 60_000, intervals: [300, 600, 1_000] }).toBe('done')
}

// TC-NEW-FBS-LIVE-001 — no route mocks: browser Vite-proxies to the real WMS
// API, while order/supply calls use the separately running WB emulator.
test('live FBS: emulator order appears in UI, then supply starts assembly', async ({ page }) => {
  const token = await registerFf(page)
  expect(token).not.toBe('')
  const headers = authHeaders(token)
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`

  const seller = await expectJson<Created>(await page.request.post('/api/sellers', {
    headers,
    data: { name: `Live FBS seller ${suffix}` },
  }))
  await expectJson(await page.request.patch(`/api/integrations/wildberries/sellers/${seller.id}/tokens`, {
    headers,
    data: { supplies_api_token: wbToken, marketplace_api_token: wbToken },
  }))
  const warehouse = await expectJson<Created>(await page.request.post('/api/warehouses', {
    headers,
    data: { name: `Live FBS WH ${suffix}`, code: `live-fbs-${suffix}` },
  }))
  await expectJson(await page.request.put(`/api/operations/fbs-sellers/${seller.id}/warehouse-bindings/${wbWarehouseId}`, {
    headers,
    data: { wms_warehouse_id: warehouse.id, stock_sync_enabled: false },
  }))
  await expectJson<Created>(await page.request.post('/api/products', {
    headers,
    data: {
      name: 'Live FBS emulator product', sku_code: `LIVE-FBS-${suffix}`, seller_id: seller.id,
      wb_barcode: wbBarcode,
    },
  }))

  // The emulator correctly refuses a purchase from zero stock. Seed its FBS
  // stock through the public Marketplace endpoint, not by writing its DB.
  const stock = await page.request.put(`${emuUrl}/api/v3/stocks/${wbWarehouseId}`, {
    headers: { Authorization: wbToken },
    data: { stocks: [{ chrtId: wbChrtId, amount: 1 }] },
  })
  expect(stock.status(), await stock.text()).toBe(204)
  const seeded = await expectJson<{ created: number; rejected_no_stock: number }>(await page.request.post(`${emuUrl}/__admin/orders?seller=${wbSellerKey}&count=1`, {
    headers: { 'X-Admin-Token': emuAdminToken },
  }))
  expect(seeded).toMatchObject({ created: 1, rejected_no_stock: 0 })
  const sync = await expectJson<{ id: string }>(await page.request.post('/api/operations/fbs-orders/sync', {
    headers,
    data: { seller_id: seller.id },
  }))
  await waitForJob(page.request, token, sync.id)

  await page.goto('/app/ff/fbs')
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-order-row')).toHaveCount(1)
  await page.getByTestId('fbs-order-checkbox').click()
  await page.getByTestId('fbs-create-supply').click()
  await page.getByTestId('fbs-create-supply-submit').click()
  await expect(page.getByTestId('fbs-supply-drawer')).toBeVisible()
  await expect(page.getByTestId('fbs-supply-start-assembly')).toBeVisible()
  await page.getByTestId('fbs-supply-start-assembly').click()
  await expect(page.getByTestId('fbs-supply-open-packaging')).toBeVisible()
})
