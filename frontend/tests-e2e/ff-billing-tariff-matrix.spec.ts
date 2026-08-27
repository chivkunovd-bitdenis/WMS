import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { openFulfillmentRegistration } from './auth-flow'
import { waitForGetOk, waitForPostOk, waitForPutOk } from './api-waits'

const UI_INVARIANTS_SOURCE = readFileSync(
  new URL('../../scripts/ui/invariants.js', import.meta.url),
  'utf8',
)

// Раздел «Ставки селлеров» ниже проверяется на НАСТОЯЩЕМ backend (uvicorn +
// sqlite), как остальной файл уже проверяет через page.route на подменённых
// данных — но именно подмена один раз скрыла реальную нестыковку экрана и
// сервера. Новые тесты снизу используют реальные HTTP-запросы (регистрация,
// создание селлера) по образцу frontend/tests-e2e/billing-invoice-v2.spec.ts.
const API = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

async function registerFfAdmin(page: Page, suffix: string): Promise<string> {
  await page.goto('/')
  await openFulfillmentRegistration(page)
  const form = page.getByTestId('register-form')
  await form.getByLabel('Организация').fill(`Тарифы селлеров ${suffix}`)
  await form.getByLabel('Email администратора').fill(`tariff-seller-rate-${suffix}@example.com`)
  await form.getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    form.getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token, 'после регистрации должен быть токен ФФ').toBeTruthy()
  return token as string
}

async function createSeller(request: APIRequestContext, token: string, name: string): Promise<string> {
  const response = await request.post(`${API}/sellers`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return (await response.json()).id as string
}


/**
 * Раскрыть селлера в таблице «Ставки селлеров».
 *
 * Плоских форм с выпадающим списком селлера больше нет: его ставки и цены на
 * его товары живут под его же строкой (просьба владельца 27.08.2026).
 */
async function expandSeller(page: Page, name: string) {
  await page
    .getByTestId('ff-settings-tariff-sellers')
    .locator('tbody tr', { hasText: name })
    .first()
    .getByRole('button')
    .first()
    .click()
}

// TC-NEW-2B-001 — Given an FF admin opens the existing settings tariff link,
// When the matrix loads, Then the stable S-19 section is visible without a new route.
test('S-19 tariff matrix accepts existing deep link', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify([{
      id: 'employee-tariff-1', email: 'operator@example.test', role: 'fulfillment_staff', must_set_password: false, packaging_rate_rub: '12.50',
      permissions: { settings: false, mp_shipments: false, reception: false, cells: false, inventory: false, packaging: true },
    }]),
  }))
  const matrix = { revision: 0, services: [
      { service_code: 'inbound', enabled: false, unit: 'document', rate: 1250, valid_from_at: '2026-08-27T09:00:00Z' },
      { service_code: 'marketplace_outbound', enabled: false, unit: null, rate: null, valid_from_at: null },
      { service_code: 'packing', enabled: false, unit: null, rate: null, valid_from_at: null },
      { service_code: 'return', enabled: false, unit: null, rate: null, valid_from_at: null },
    ], versions: [{ seller_id: null, product_id: null, employee_user_id: null, service_code: 'inbound', unit: 'document', enabled: true, rate: 1250, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null }], products: [{ id: 'product-tariff-1', seller_id: 'seller-tariff-1', seller_name: 'Селлер Тест', sku: 'SKU-001', name: 'Куртка', label: 'Селлер Тест · SKU-001 · Куртка' }], sellers: [{ id: 'seller-tariff-1', name: 'Селлер Тест' }], storage: { mode: 'legacy_daily', editable_in_matrix: false } }
  let responseMatrix = matrix
  let putCount = 0
  let savedPayload: { services: Array<{ service_code: string; enabled: boolean }>; versions: Array<{ product_id: string | null; employee_user_id: string | null; rate: number }> } | null = null
  await page.route('**/api/billing/tariff-matrix', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseMatrix) })
      return
    }
    putCount += 1
    savedPayload = route.request().postDataJSON() as typeof savedPayload
    responseMatrix = {
      revision: 1,
      services: matrix.services.map((service) => ({ ...service, enabled: savedPayload?.services.find((row) => row.service_code === service.service_code)?.enabled ?? service.enabled })),
      versions: savedPayload?.versions ?? [], products: matrix.products, storage: matrix.storage,
    }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(responseMatrix),
    })
  })
  await page.goto('/app/ff/settings?tab=tariffs')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toBeFocused()
  await expect(panel.getByTestId('ff-settings-tariffs-services').getByRole('cell', { name: 'Приёмка', exact: true })).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariffs-services').getByRole('columnheader', { name: 'Ставка, ₽' })).toBeVisible()
  await expect(panel.getByRole('heading', { name: 'Ставки селлеров' })).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-sellers')).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates')).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates').getByRole('columnheader', { name: 'Подбор', exact: true })).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates').getByRole('columnheader', { name: 'Упаковка' })).toBeVisible()
  const inboundAction = panel.getByTestId('ff-settings-tariff-inbound')
  await expect(inboundAction).toHaveText('Включить')
  await expect(inboundAction).toHaveAttribute('aria-pressed', 'false')
  await inboundAction.click()
  await expect(inboundAction).toHaveText('Выключить')
  await expect(inboundAction).toHaveAttribute('aria-pressed', 'true')
  await expect(panel.getByTestId('ff-settings-tariff-rate-inbound')).toHaveValue('12.5')
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('33.50')
  await panel.getByTestId('ff-settings-tariff-unit-inbound').selectOption('item')
  await expandSeller(page, 'Селлер Тест')
  // Внутри селлера имя из подписи товара уходит: и так видно, чей это товар.
  await panel.getByTestId('ff-settings-tariff-target-seller-tariff-1').selectOption('product-tariff-1')
  await expect(panel.getByTestId('ff-settings-tariff-target-seller-tariff-1')).toContainText('SKU-001 · Куртка')
  await panel.getByTestId('ff-settings-tariff-rate-seller-tariff-1').fill('17.50')
  await panel.getByTestId('ff-settings-tariff-add-seller-tariff-1').click()
  await panel.getByTestId('ff-settings-tariff-employee-employee-tariff-1-inbound').fill('21.50')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-success')).toBeVisible()
  expect(putCount).toBe(1)
  expect(savedPayload?.services.find((row) => row.service_code === 'inbound')?.enabled).toBe(true)
  expect(savedPayload?.versions.some((row) => row.product_id === 'product-tariff-1' && row.rate === 1750)).toBe(true)
  expect(savedPayload?.versions.some((row) => row.employee_user_id === 'employee-tariff-1' && row.rate === 2150)).toBe(true)
  expect(savedPayload?.versions.some((row) => row.product_id === null && row.employee_user_id === null && row.rate === 1250)).toBe(true)
  expect(savedPayload?.versions.some((row) => row.product_id === null && row.employee_user_id === null && row.rate === 3350)).toBe(true)
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('33.501')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-error')).toContainText('Ставка указывается в рублях')
  expect(putCount).toBe(1)
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('21474836.48')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-error')).toContainText('21 474 836,47 ₽')
  expect(putCount).toBe(1)
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('0.29')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-success')).toBeVisible()
  expect(putCount).toBe(2)
  expect(savedPayload?.versions.some((row) => row.product_id === null && row.employee_user_id === null && row.rate === 29)).toBe(true)
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('34')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-success')).toBeVisible()
  expect(putCount).toBe(3)
  expect(savedPayload?.versions.some((row) => row.product_id === null && row.employee_user_id === null && row.rate === 3400)).toBe(true)
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).toContainText('Селлер Тест · SKU-001 · Куртка')
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).not.toContainText('product-tariff-1')
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).toContainText('17,50')
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).toContainText(/\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}/)
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).not.toContainText('T')
  await expect(panel.getByTestId('ff-settings-tariff-storage-link')).toHaveAttribute('href', '/app/ff/inventory')
  await expect(panel.getByTestId('ff-settings-tariff-storage-state')).toHaveText('Отдельно')
  await page.reload()
  await expect(page.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).toContainText('Селлер Тест · SKU-001 · Куртка')
  await expect(page.getByTestId('ff-settings-tariff-employee-rates')).toContainText('operator@example.test')
})

test('S-19 keeps normal scroll, protects document product overrides and shows stale save error', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }) }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  const matrix = {
    revision: 4,
    services: [
      { service_code: 'inbound', enabled: true, unit: 'document', rate: 1250, valid_from_at: '2026-08-27T09:00:00Z' },
      { service_code: 'marketplace_outbound', enabled: false, unit: null, rate: null, valid_from_at: null },
      { service_code: 'packing', enabled: false, unit: null, rate: null, valid_from_at: null },
      { service_code: 'return', enabled: false, unit: null, rate: null, valid_from_at: null },
    ],
    versions: [{ seller_id: null, product_id: null, employee_user_id: null, service_code: 'inbound', unit: 'document', enabled: true, rate: 1250, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null }],
    products: [{ id: 'product-doc-1', seller_id: 'seller-doc-1', seller_name: 'Селлер Документ', sku: 'DOC-01', name: 'Платье', label: 'Селлер Документ · DOC-01 · Платье' }], sellers: [{ id: 'seller-doc-1', name: 'Селлер Документ' }],
    storage: { mode: 'legacy_daily', editable_in_matrix: false },
  }
  await page.route('**/api/billing/tariff-matrix', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(matrix) })
      return
    }
    await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'billing_tariff_matrix_stale_revision' }) })
  })
  await page.goto('/app/ff/settings')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  await expect(panel).not.toBeFocused()
  await expect(panel.getByTestId('ff-settings-tariff-product-unit-boundary')).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-product-add')).toBeDisabled()
  await expect(panel.getByTestId('ff-settings-tariff-storage-link')).toHaveAttribute('href', '/app/ff/inventory')
  await expect(panel.getByTestId('ff-settings-tariffs-services').getByRole('columnheader', { name: 'Ставка, ₽' })).toBeVisible()
  expect(await panel.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await panel.getByTestId('ff-settings-tariff-rate-inbound').fill('1300')
  await panel.getByTestId('ff-settings-tariffs-save').click()
  await expect(panel.getByTestId('ff-settings-tariffs-error')).toContainText('Конфигурация тарифов уже изменилась. Обновите данные и повторите сохранение.')
})

test('S-19 brand-new per-item default permits a product override', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }) }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/api/billing/tariff-matrix', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    revision: 0,
    services: ['inbound', 'marketplace_outbound', 'packing', 'return'].map((service_code) => ({ service_code, enabled: false, unit: 'item', rate: null, valid_from_at: null })),
    versions: [], products: [{ id: 'new-product-1', seller_id: 'new-seller-1', seller_name: 'Новый селлер', sku: 'NEW-01', name: 'Новый товар', label: 'Новый селлер · NEW-01 · Новый товар' }], sellers: [{ id: 'new-seller-1', name: 'Новый селлер' }], storage: { mode: 'legacy_daily', editable_in_matrix: false },
  }) }))
  await page.goto('/app/ff/settings')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel.getByTestId('ff-settings-tariff-product-unit-boundary')).toHaveCount(0)
  await expect(panel.getByTestId('ff-settings-tariff-product-add')).toBeEnabled()
})

// TC-NEW-2B-014 — Given a fully populated tariff matrix at the narrow operator viewport,
// When the settings panel renders its real service, product, and employee rows,
// Then only DataTable containers may scroll horizontally and the document stays within 1280 px.
test('S-19 confines populated tariff matrix overflow to DataTable containers at 375–1600', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    // Matrix versions still populate its employee-rate table below.  Keep the
    // unrelated legacy staff table empty, so this geometry guard diagnoses the
    // S-19 tariff panel rather than a pre-existing Settings table.
    body: '[]',
  }))
  await page.route('**/api/billing/tariff-matrix', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      revision: 7,
      services: [
        { service_code: 'inbound', enabled: true, unit: 'item', rate: 1250, valid_from_at: '2026-08-27T09:00:00Z' },
        { service_code: 'marketplace_outbound', enabled: true, unit: 'document', rate: 9500, valid_from_at: '2026-08-27T09:00:00Z' },
        { service_code: 'packing', enabled: true, unit: 'item', rate: 500, valid_from_at: '2026-08-27T09:00:00Z' },
        { service_code: 'return', enabled: false, unit: 'item', rate: 300, valid_from_at: '2026-08-27T09:00:00Z' },
      ],
      versions: [
        { seller_id: 'seller-wide-1', product_id: 'product-wide-1', employee_user_id: null, service_code: 'inbound', unit: 'item', enabled: true, rate: 1500, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null },
        { seller_id: 'seller-wide-2', product_id: 'product-wide-2', employee_user_id: null, service_code: 'packing', unit: 'item', enabled: true, rate: 750, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null },
        { seller_id: null, product_id: null, employee_user_id: 'employee-wide-1', service_code: 'inbound', unit: 'item', enabled: true, rate: 200, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null },
        { seller_id: null, product_id: null, employee_user_id: 'employee-wide-2', service_code: 'return', unit: 'item', enabled: true, rate: 250, valid_from_at: '2026-08-27T09:00:00Z', valid_to_at: null },
      ],
      products: [
        { id: 'product-wide-1', seller_id: 'seller-wide-1', seller_name: 'Селлер Север', sku: 'NORTH-001', name: 'Куртка зимняя', label: 'Селлер Север · NORTH-001 · Куртка зимняя' },
        { id: 'product-wide-2', seller_id: 'seller-wide-2', seller_name: 'Селлер Юг', sku: 'SOUTH-002', name: 'Платье вечернее', label: 'Селлер Юг · SOUTH-002 · Платье вечернее' },
      ], sellers: [{ id: 'seller-wide-1', name: 'Селлер Север' }, { id: 'seller-wide-2', name: 'Селлер Юг' }],
      storage: { mode: 'legacy_daily', editable_in_matrix: false },
    }),
  }))

  await page.goto('/app/ff/settings?tab=tariffs')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariffs-services').getByRole('row')).toHaveCount(5)
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1').getByRole('row')).toHaveCount(3)
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates').getByRole('row')).toHaveCount(3)

  for (const width of [768, 1280, 1600]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(panel).toBeVisible()
    const geometryAtViewport = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      offenders: [...document.querySelectorAll<HTMLElement>('body *')]
        .map((element) => ({
          testId: element.dataset.testid ?? '',
          tag: element.tagName,
          width: Math.round(element.getBoundingClientRect().width),
          right: Math.round(element.getBoundingClientRect().right),
        }))
        .filter((element) => element.right > window.innerWidth + 1)
        .slice(0, 8),
    }))
    expect(
      geometryAtViewport.documentWidth,
      `viewport ${width}, ${JSON.stringify(geometryAtViewport)}`,
    ).toBeLessThanOrEqual(width)
  }
  await page.setViewportSize({ width: 1280, height: 1000 })
  const geometry = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>('[data-testid="ff-settings-tariffs-panel"]')
    const tables = [...document.querySelectorAll<HTMLElement>(
      '[data-testid="ff-settings-tariffs-services"], [data-testid="ff-settings-tariff-sellers"], [data-testid="ff-settings-tariff-employee-rates"]',
    )]
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      panelWidth: panel?.clientWidth ?? 0,
      tables: tables.map((table) => ({
        testId: table.dataset.testid,
        clientWidth: table.clientWidth,
        scrollWidth: table.scrollWidth,
      })),
      offenders: [...document.querySelectorAll<HTMLElement>('body *')]
        .map((element) => ({
          testId: element.dataset.testid ?? '',
          tag: element.tagName,
          right: Math.round(element.getBoundingClientRect().right),
          width: Math.round(element.getBoundingClientRect().width),
        }))
        .filter((element) => element.right > window.innerWidth + 1)
        .slice(0, 12),
      scrolling: [...document.querySelectorAll<HTMLElement>('body *')]
        .map((element) => ({
          testId: element.dataset.testid ?? '',
          tag: element.tagName,
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
        }))
        .filter((element) => element.scrollWidth > element.clientWidth + 1)
        .slice(0, 12),
    }
  })
  expect(geometry.documentWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewportWidth)
  for (const table of geometry.tables) {
    expect(table.clientWidth, table.testId).toBeLessThanOrEqual(geometry.panelWidth)
  }
  const serviceTable = geometry.tables.find((table) => table.testId === 'ff-settings-tariffs-services')
  expect(serviceTable?.scrollWidth).toBeGreaterThan(serviceTable?.clientWidth ?? 0)

  // Keep the browser assertion byte-for-byte aligned with scripts/ui/invariants.js.
  const invariants = JSON.parse(await page.evaluate((source) => eval(source), UI_INVARIANTS_SOURCE)) as {
    ok: boolean
    violations: Array<{ rule: string; what: string; sample: string }>
  }
  expect(invariants.violations.filter((violation) => violation.rule === 'R-01' || violation.rule === 'R-08')).toEqual([])
  expect(invariants.ok, JSON.stringify(invariants.violations)).toBe(true)

  await page.setViewportSize({ width: 375, height: 1000 })
  const narrow = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>('[data-testid="ff-settings-tariffs-panel"]')
    const content = document.querySelector<HTMLElement>('[data-testid="app-content"]')
    const requiredControls = [
      'ff-settings-tariff-sellers',
      'ff-settings-tariffs-save',
    ].map((testId) => document.querySelector<HTMLElement>(`[data-testid="${testId}"]`))
    const status = document.querySelector<HTMLElement>('[data-testid="ff-settings-tariff-state-inbound"]')
    const storageStatus = document.querySelector<HTMLElement>('[data-testid="ff-settings-tariff-storage-state"]')
    const nonTableOverflow = [...(panel?.querySelectorAll<HTMLElement>('*') ?? [])]
      .filter((element) => element.scrollWidth > element.clientWidth + 1)
      .filter((element) => ['auto', 'scroll'].includes(getComputedStyle(element).overflowX))
      .filter((element) => !element.closest('.MuiTableContainer-root'))
      .map((element) => element.dataset.testid ?? element.tagName)
    const withPanel = document.documentElement.scrollWidth
    const panelWidth = panel?.clientWidth ?? 0
    const panelRight = Math.round(panel?.getBoundingClientRect().right ?? 0)
    const contentRight = Math.round(content?.getBoundingClientRect().right ?? 0)
    const controlsInsidePanel = requiredControls.every((element) => {
      if (!element || !panel) return false
      const rect = element.getBoundingClientRect()
      const panelRect = panel.getBoundingClientRect()
      return rect.left >= panelRect.left - 1 && rect.right <= panelRect.right + 1
    })
    panel?.remove()
    return {
      withPanel,
      withoutPanel: document.documentElement.scrollWidth,
      panelWidth,
      panelRight,
      contentRight,
      withoutContentRight: Math.round(content?.getBoundingClientRect().right ?? 0),
      controlsInsidePanel,
      statusInsidePanel: Boolean(status && panel?.contains(status) && status.closest('.MuiTableContainer-root')),
      storageStatusInsidePanel: Boolean(storageStatus && panel?.contains(storageStatus)
        && storageStatus.getBoundingClientRect().right <= (panel?.getBoundingClientRect().right ?? 0) + 1),
      nonTableOverflow,
    }
  })
  // The existing desktop shell itself is wider than a phone viewport.  The
  // matrix must still have a real, non-negative available width and may not
  // make that inherited shell overflow worse.
  expect(narrow.panelWidth).toBeGreaterThan(0)
  expect(narrow.withPanel).toBeLessThanOrEqual(narrow.withoutPanel)
  expect(narrow.panelRight).toBeLessThanOrEqual(narrow.withoutContentRight)
  expect(narrow.contentRight).toBeLessThanOrEqual(narrow.withoutContentRight)
  expect(narrow.controlsInsidePanel).toBe(true)
  expect(narrow.statusInsidePanel).toBe(true)
  expect(narrow.storageStatusInsidePanel).toBe(true)
  expect(narrow.nonTableOverflow).toEqual([])
})

// TC-NEW-2B-016 — a held matrix response must keep dependent tables in their
// loading state rather than falsely claiming that products or staff are empty.
test('S-19 keeps product and employee tables loading until the matrix GET resolves', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '[]',
  }))
  let releaseMatrix: (() => void) | undefined
  let markRequested: (() => void) | undefined
  const requested = new Promise<void>((resolve) => { markRequested = resolve })
  await page.route('**/api/billing/tariff-matrix', async (route) => {
    markRequested?.()
    await new Promise<void>((resolve) => { releaseMatrix = resolve })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        revision: 0,
        services: ['inbound', 'marketplace_outbound', 'packing', 'return'].map((service_code) => ({
          service_code, enabled: false, unit: 'item', rate: null, valid_from_at: null,
        })),
        versions: [], products: [], sellers: [], storage: { mode: 'legacy_daily', editable_in_matrix: false },
      }),
    })
  })
  await page.goto('/app/ff/settings')
  await requested
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).not.toContainText('Товарных цен пока нет')
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates')).not.toContainText('Сотрудников пока нет')
  releaseMatrix?.()
  await expect(panel.getByTestId('ff-settings-tariff-seller-own-seller-tariff-1')).toContainText('Товарных цен пока нет')
  await expect(panel.getByTestId('ff-settings-tariff-employee-rates')).toContainText('Сотрудников пока нет')
})

// TC-NEW-2B-015 — The legacy staff table is outside the tariff-panel scope.
// Keep a same-state A/B measurement so a panel fix cannot be credited for an
// inherited Settings R-01, or hide a regression behind an empty staff fixture.
test('S-19 tariff panel does not worsen inherited 1280 staff-table width', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([
      { id: 'employee-baseline-1', email: 'anna.ivanova@example.test', role: 'fulfillment_staff', must_set_password: false, packaging_rate_rub: '12.50', permissions: {} },
      { id: 'employee-baseline-2', email: 'boris.petrov@example.test', role: 'fulfillment_staff', must_set_password: false, packaging_rate_rub: '10.00', permissions: {} },
    ]),
  }))
  await page.route('**/api/billing/tariff-matrix', async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      revision: 8,
      services: ['inbound', 'marketplace_outbound', 'packing', 'return'].map((service_code) => ({
        service_code, enabled: true, unit: 'item', rate: 1000, valid_from_at: '2026-08-27T09:00:00Z',
      })),
      versions: [],
      products: [{ id: 'product-baseline-1', seller_id: 'seller-baseline-1', seller_name: 'Селлер База', sku: 'BASE-01', name: 'Товар', label: 'Селлер База · BASE-01 · Товар' }], sellers: [{ id: 'seller-baseline-1', name: 'Селлер База' }],
      storage: { mode: 'legacy_daily', editable_in_matrix: false },
    }),
  }))

  await page.goto('/app/ff/settings')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  const withPanel = await page.evaluate(() => document.documentElement.scrollWidth)
  const withoutPanel = await panel.evaluate((element) => {
    element.remove()
    return document.documentElement.scrollWidth
  })

  expect(withoutPanel).toBeGreaterThan(1280)
  expect(withPanel).toBeLessThanOrEqual(withoutPanel)
})
