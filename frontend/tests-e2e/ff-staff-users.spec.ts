import { expect, test, type Page } from '@playwright/test'

import { waitForGetOk, waitForPatchOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

type StaffPermissions = {
  settings: boolean
  mp_shipments: boolean
  reception: boolean
  cells: boolean
  inventory: boolean
  packaging: boolean
  shift_lead: boolean
}

const NO_PERMISSIONS: StaffPermissions = {
  settings: false,
  mp_shipments: false,
  reception: false,
  cells: false,
  inventory: false,
  packaging: false,
  shift_lead: false,
}

async function loginToken(page: Page, email: string, password: string): Promise<string> {
  const res = await page.request.post('/api/auth/login', {
    data: { email, password },
  })
  expect(res.ok()).toBeTruthy()
  return String(((await res.json()) as { access_token: string }).access_token)
}

async function createStaffViaApi(
  page: Page,
  adminHeaders: Record<string, string>,
  email: string,
  permissions: Partial<StaffPermissions>,
): Promise<{ id: string; token: string }> {
  const created = await page.request.post('/api/auth/staff-accounts', {
    headers: adminHeaders,
    data: { email },
  })
  expect(created.status()).toBe(201)
  const body = (await created.json()) as { id: string }
  const patched = await page.request.patch(`/api/auth/staff-accounts/${body.id}/permissions`, {
    headers: adminHeaders,
    data: { ...NO_PERMISSIONS, ...permissions },
  })
  expect(patched.status()).toBe(200)
  const password = 'password123'
  const setup = await page.request.post('/api/auth/set-initial-password', {
    data: { email, password },
  })
  expect(setup.status()).toBe(200)
  return { id: body.id, token: await loginToken(page, email, password) }
}

async function useFulfillmentToken(page: Page, token: string): Promise<void> {
  await page.evaluate((nextToken) => {
    localStorage.setItem('wms_token_ff', nextToken)
    localStorage.removeItem('wms_token')
  }, token)
}

async function expectDenied(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await expect(page.getByTestId('ff-access-denied')).toContainText('Нет доступа к этому разделу.')
}

async function expectSellerPortalDenied(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await expect(page.getByTestId('ff-access-denied')).toContainText(
    'В этом браузере нет сессии селлера',
  )
}

async function expectNoPayrollUi(page: Page): Promise<void> {
  await expect(page.getByText('Месяц расчёта')).toHaveCount(0)
  await expect(page.getByText('Ставка за ед.')).toHaveCount(0)
  await expect(page.getByText('Упаковано')).toHaveCount(0)
  await expect(page.getByText('Начислено')).toHaveCount(0)
  await expect(page.getByText('Старший смены')).toHaveCount(0)
}

// TC-NEW-001 — F14: FF admin creates staff, four compact rights map to real routes.
// Given: FF admin adds staff users; When: each user logs in and opens their section;
// Then: only the right warehouse work block is clickable, direct forbidden routes are closed,
// expected: settings-staff sees no payroll columns, raw permission labels, or technical error codes.
test('ff staff rights: four compact work blocks pass UI and direct-route gates', async ({ page }) => {
  // Тест тяжёлый: регистрация организации, шесть сотрудников по четыре запроса
  // на каждого и полтора десятка полных перезагрузок SPA. При лимите 120 с запаса
  // не оставалось вовсе (18.08 шёл 1.7 мин), и под нагрузкой машины он падал
  // по времени, а не по существу — при 300 с проходит целиком, включая проверки
  // закрытых разделов. Даём реальный запас.
  test.setTimeout(240_000)
  const suffix = Date.now()
  const adminEmail = `e2e-staff-admin-${suffix}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Staff Users')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const [registerRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const adminToken = String(((await registerRes.json()) as { access_token: string }).access_token)
  const adminHeaders = { Authorization: `Bearer ${adminToken}` }

  await page.getByTestId('nav-ff-settings').click()
  await expect(page).toHaveURL(/\/app\/ff\/settings/)
  await expect(page.getByTestId('ff-staff-empty')).toBeVisible()
  await expect(page.getByTestId('ff-staff-billing-month')).toBeVisible()
  await expect(page.getByText('Старший смены')).toHaveCount(0)

  const firstStaffEmail = `e2e-staff-reception-ui-${suffix}@example.com`
  await page.getByTestId('ff-staff-email').fill(firstStaffEmail)
  await Promise.all([
    waitForPostOk(page, '/api/auth/staff-accounts'),
    waitForGetOk(page, '/api/auth/staff-accounts'),
    page.getByTestId('ff-staff-submit').click(),
  ])
  await expect(page.getByTestId('ff-settings-users-success')).toHaveText('Сотрудник добавлен')
  const firstStaffRow = page.getByTestId('ff-staff-row').filter({ hasText: firstStaffEmail })
  await expect(firstStaffRow).toBeVisible()
  const staffTable = page.getByTestId('ff-staff-table')
  await expect(staffTable.getByText('Приёмка', { exact: true })).toBeVisible()
  await expect(staffTable.getByText('Отгрузки', { exact: true })).toBeVisible()
  await expect(staffTable.getByText('Каталог и ячейки', { exact: true })).toBeVisible()
  await expect(staffTable.getByText('Настройки и сотрудники', { exact: true })).toBeVisible()

  const firstStaffId = await firstStaffRow.getAttribute('data-staff-id')
  expect(firstStaffId).toBeTruthy()
  await Promise.all([
    waitForPatchOk(page, `/api/auth/staff-accounts/${firstStaffId}/permissions`),
    firstStaffRow.getByTestId(`ff-staff-access-${firstStaffId}-reception`).click(),
  ])
  await expect(page.getByTestId('ff-staff-perm-saved')).toContainText('Права сохранены')

  const duplicate = await page.request.post('/api/auth/staff-accounts', {
    headers: adminHeaders,
    data: { email: firstStaffEmail },
  })
  expect(duplicate.status()).toBe(409)
  await page.getByTestId('ff-staff-email').fill(firstStaffEmail)
  await page.getByTestId('ff-staff-submit').click()
  await expect(page.getByTestId('ff-settings-users-error')).toContainText('Этот сотрудник уже добавлен')
  await expect(page.getByTestId('ff-settings-users-error')).not.toContainText('email_taken')

  const receptionToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-reception-${suffix}@example.com`, {
    reception: true,
  })).token
  const shipmentsToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-shipments-${suffix}@example.com`, {
    mp_shipments: true,
    packaging: true,
    shift_lead: true,
  })).token
  const cellsToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-cells-${suffix}@example.com`, {
    cells: true,
    inventory: true,
  })).token
  const settingsToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-settings-${suffix}@example.com`, {
    settings: true,
  })).token
  const mpOnlyToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-mp-only-${suffix}@example.com`, {
    mp_shipments: true,
  })).token
  const packagingOnlyToken = (await createStaffViaApi(page, adminHeaders, `e2e-staff-packaging-only-${suffix}@example.com`, {
    packaging: true,
  })).token

  await useFulfillmentToken(page, receptionToken)
  await page.goto('/app/ff/reception')
  await expect(page.getByTestId('ff-reception-page')).toBeVisible()
  await expect(page.getByTestId('nav-ff-reception')).toBeVisible()
  await expect(page.getByTestId('nav-ff-sorting')).toBeVisible()
  await expect(page.getByTestId('nav-ff-mp-shipments')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-fbs')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-packaging')).toHaveCount(0)
  await expect(page.getByTestId('nav-catalog')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-inventory')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-settings')).toHaveCount(0)
  await expect(page.getByText('forbidden')).toHaveCount(0)
  await expectDenied(page, '/app/ff/mp-shipments')
  await expectDenied(page, '/app/ff/settings')
  await expectDenied(page, '/app/catalog')
  await expectDenied(page, '/app/ff/fbs')
  await expectDenied(page, '/app/ff/packaging')
  await expectDenied(page, '/app/ff/inventory')
  await expectDenied(page, '/app/ff/sellers')
  await expectSellerPortalDenied(page, '/seller/products')

  await useFulfillmentToken(page, shipmentsToken)
  await page.goto('/app/ff/mp-shipments')
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()
  await expect(page.getByTestId('nav-ff-mp-shipments')).toBeVisible()
  await expect(page.getByTestId('nav-ff-fbs')).toBeVisible()
  await expect(page.getByTestId('nav-ff-packaging')).toBeVisible()
  await expect(page.getByTestId('nav-ff-reception')).toHaveCount(0)
  await expect(page.getByTestId('nav-catalog')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-inventory')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-settings')).toHaveCount(0)
  await page.getByTestId('nav-ff-fbs').click()
  await expect(page).toHaveURL(/\/app\/ff\/fbs/)
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('fbs-orders-sync-wb')).toHaveCount(0)
  await expect(page.getByTestId('fbs-nav-stock-sync')).toHaveCount(0)
  await page.getByTestId('nav-ff-packaging').click()
  await expect(page).toHaveURL(/\/app\/ff\/packaging/)
  await expect(page.getByTestId('ff-packaging-page')).toBeVisible()
  await page.goto('/app/ff/packaging/pending-marking')
  await expect(page.getByTestId('ff-pending-marking-page')).toBeVisible()
  await page.goto('/app/ff/fbs')
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await page.goto('/app/ff/packaging')
  await expect(page.getByTestId('ff-packaging-page')).toBeVisible()
  await expectDenied(page, '/app/ff/reception')
  await expectDenied(page, '/app/ff/settings')
  await expectDenied(page, '/app/catalog')
  await expectDenied(page, '/app/ff/inventory')
  await expectDenied(page, '/app/ff/sellers')
  await expectDenied(page, '/app/ff/fbs/stock-sync')

  await useFulfillmentToken(page, mpOnlyToken)
  await page.goto('/app/ff/mp-shipments')
  await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()
  await expect(page.getByTestId('nav-ff-mp-shipments')).toBeVisible()
  await expect(page.getByTestId('nav-ff-fbs')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-packaging')).toHaveCount(0)
  await expectDenied(page, '/app/ff/fbs')
  await expectDenied(page, '/app/ff/packaging')
  await expectDenied(page, '/app/ff/honest-sign/reprints')

  await useFulfillmentToken(page, packagingOnlyToken)
  await page.goto('/app/ff/fbs')
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await expect(page.getByTestId('nav-ff-mp-shipments')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-fbs')).toBeVisible()
  await expect(page.getByTestId('nav-ff-packaging')).toBeVisible()
  await page.getByTestId('nav-ff-packaging').click()
  await expect(page).toHaveURL(/\/app\/ff\/packaging/)
  await expect(page.getByTestId('ff-packaging-page')).toBeVisible()
  await expectDenied(page, '/app/ff/mp-shipments')
  await expectDenied(page, '/app/ff/honest-sign/reprints')

  await useFulfillmentToken(page, cellsToken)
  await page.goto('/app/ff/products')
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('nav-catalog')).toBeVisible()
  await expect(page.getByTestId('nav-ff-inventory')).toHaveCount(0)
  await expect(page.getByTestId('nav-catalog')).toContainText('Каталог и ячейки')
  await page.getByTestId('nav-catalog').click()
  await expect(page).toHaveURL(/\/app\/ff\/products/)
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('nav-ff-reception')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-mp-shipments')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-fbs')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-packaging')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-settings')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-create-seller')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-import-tz')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-create')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-seller-filter')).toHaveCount(0)
  await expect(page.locator('[data-testid^="ff-packaging-edit-"]')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-error')).toHaveCount(0)
  await page.goto('/app/ff/inventory')
  await expect(page).toHaveURL(/\/app\/ff\/inventory/)
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await expectDenied(page, '/app/ff/settings')
  await expectDenied(page, '/app/ff/mp-shipments')
  await expectDenied(page, '/app/ff/fbs')
  await expectDenied(page, '/app/ff/packaging')
  await expectDenied(page, '/app/ff/reception')
  await expectDenied(page, '/app/ff/sellers')
  await expectDenied(page, '/app/catalog/products')

  await useFulfillmentToken(page, settingsToken)
  await page.goto('/app/ff/settings')
  await expect(page.getByTestId('ff-settings-screen')).toBeVisible()
  await expect(page.getByTestId('ff-settings-users-panel')).toBeVisible()
  await expect(page.getByTestId('nav-ff-settings')).toBeVisible()
  await expect(page.getByTestId('nav-ff-reception')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-mp-shipments')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-fbs')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-packaging')).toHaveCount(0)
  await expect(page.getByTestId('nav-catalog')).toHaveCount(0)
  await expect(page.getByTestId('nav-ff-inventory')).toHaveCount(0)
  await expectNoPayrollUi(page)
  await expect(page.getByText('forbidden')).toHaveCount(0)
  await expectDenied(page, '/app/ff/reception')
  await expectDenied(page, '/app/ff/mp-shipments')
  await expectDenied(page, '/app/ff/fbs')
  await expectDenied(page, '/app/ff/packaging')
  await expectDenied(page, '/app/catalog')
  await expectDenied(page, '/app/ff/inventory')
  await expectDenied(page, '/app/ff/sellers')
  await expectDenied(page, '/app/ops/inbound')

  const settingsHeaders = { Authorization: `Bearer ${settingsToken}` }
  const staffList = await page.request.get('/api/auth/staff-accounts', { headers: settingsHeaders })
  expect(staffList.status()).toBe(200)
  const staffRows = (await staffList.json()) as Record<string, unknown>[]
  expect(staffRows.length).toBeGreaterThan(0)
  expect(staffRows.every((row) => !('packaging_rate_rub' in row))).toBeTruthy()
  expect(staffRows.every((row) => !('packaging_billing' in row))).toBeTruthy()
  const settingsTargetStaffId = String(staffRows[0]?.id ?? '')
  expect(settingsTargetStaffId).toBeTruthy()
  const settingsRatePatch = await page.request.patch(`/api/auth/staff-accounts/${settingsTargetStaffId}/packaging-rate`, {
    headers: settingsHeaders,
    data: { rate_rub: '12.50' },
  })
  expect(settingsRatePatch.status()).toBe(403)
  expect((await page.request.get('/api/products', { headers: settingsHeaders })).status()).toBe(403)
  expect((await page.request.get('/api/operations/inventory-balances/summary', { headers: settingsHeaders })).status()).toBe(403)
  expect((await page.request.get('/api/operations/marketplace-unload-requests', { headers: settingsHeaders })).status()).toBe(403)
})
