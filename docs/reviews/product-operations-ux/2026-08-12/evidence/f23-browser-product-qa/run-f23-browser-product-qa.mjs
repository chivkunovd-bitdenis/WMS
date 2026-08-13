import fs from 'node:fs/promises'
import path from 'node:path'

import { chromium } from '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend/node_modules/playwright/index.mjs'

const root = path.resolve(import.meta.dirname)
const screenshotsDir = path.join(root, 'screenshots')
const webOrigin = process.env.E2E_WEB_ORIGIN ?? 'http://127.0.0.1:5179'
const apiOrigin = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18123'
const suffix = String(Date.now())
const adminEmail = `f23-browser-qa-admin-${suffix}@example.com`
const sellerEmail = `f23-browser-qa-seller-${suffix}@example.com`
const password = 'password123'
const sku = `F23-QA-${suffix}`

const evidence = {
  verdict: 'FAILED',
  webOrigin,
  apiOrigin,
  suffix,
  productId: null,
  screenshots: [],
  checks: {},
  bulkPatchBody: null,
  geometry1280: null,
}

function expect(condition, message) {
  if (!condition) throw new Error(message)
}

async function shot(page, name) {
  const file = path.join(screenshotsDir, `${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  evidence.screenshots.push(path.relative(root, file))
}

async function api(page, method, url, token, data) {
  const res = await page.request[method](`${apiOrigin}${url}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data,
  })
  if (!res.ok()) {
    throw new Error(`${method.toUpperCase()} ${url}: ${res.status()} ${await res.text()}`)
  }
  if (res.status() === 204) return null
  return res.json()
}

async function main() {
  await fs.mkdir(screenshotsDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } })
  const page = await context.newPage()

  try {
    await page.goto(webOrigin)
    await page.getByTestId('go-to-register').click()
    await page.getByTestId('register-form').waitFor({ state: 'visible' })
    await page.getByTestId('register-form').getByLabel('Организация').fill('F23 Browser QA')
    await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
    await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
    const [registerResponse] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/auth/register') && r.status() === 200),
      page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
    ])
    const token = (await registerResponse.json()).access_token

    const seller = await api(page, 'post', '/sellers', token, { name: 'F23 Seller QA' })
    await api(page, 'post', '/auth/seller-accounts', token, {
      seller_id: seller.id,
      email: sellerEmail,
    })
    const warehouse = await api(page, 'post', '/warehouses', token, {
      name: 'F23 WH',
      code: `f23-wh-${suffix}`,
    })
    const location = await api(page, 'post', `/warehouses/${warehouse.id}/locations`, token, {
      code: 'F23-LOC',
    })
    const product = await api(page, 'post', '/products', token, {
      name: 'F23 QA Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: seller.id,
    })
    evidence.productId = product.id

    const inbound = await api(page, 'post', '/operations/inbound-intake-requests', token, {
      warehouse_id: warehouse.id,
    })
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/lines`, token, {
      product_id: product.id,
      expected_qty: 10,
      storage_location_id: location.id,
    })
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/submit`, token)
    const inboundBody = await api(page, 'get', `/operations/inbound-intake-requests/${inbound.id}`, token)
    const lineId = inboundBody.lines[0].id
    await api(page, 'patch', `/operations/inbound-intake-requests/${inbound.id}/lines/${lineId}/actual`, token, {
      actual_qty: 0,
    })
    const box = await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/boxes`, token)
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/boxes/open`, token, {
      barcode: box.internal_barcode,
    })
    for (let i = 0; i < 10; i += 1) {
      await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/boxes/${box.id}/scan`, token, {
        barcode: sku,
      })
    }
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/boxes/${box.id}/close`, token)
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/verify`, token)
    await api(page, 'post', `/operations/inbound-intake-requests/${inbound.id}/post`, token)

    await page.getByTestId('logout').click()
    await page.goto(`${webOrigin}/seller/`)
    await page.getByTestId('login-form').getByLabel('Email').fill(sellerEmail)
    await page.getByTestId('login-form').getByLabel('Пароль').fill('')
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/auth/login')),
      page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
    ])
    await page.getByTestId('seller-password-setup-form').getByLabel('Новый пароль').fill(password)
    await page.getByTestId('seller-password-setup-form').getByLabel('Повтор пароля').fill(password)
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/auth/set-initial-password') && r.status() === 200),
      page.getByTestId('seller-password-setup-submit').click(),
    ])

    await page.getByTestId('nav-seller-products').click()
    await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
    await shot(page, '01-seller-products-1280-initial')

    const bodyText = await page.locator('body').innerText()
    const forbidden = ['Лимит', 'Включить всем', 'Выключить всем', 'Пауза публикации всем']
    evidence.checks.forbiddenTextAbsent = forbidden.filter((text) => bodyText.includes(text))
    expect(evidence.checks.forbiddenTextAbsent.length === 0, `Forbidden text visible: ${evidence.checks.forbiddenTextAbsent.join(', ')}`)
    expect(!/pending_confirmation|warehouse_mapping_missing|wb_upstream_error|conflict/.test(bodyText), 'Raw technical status visible')
    await expectRowNoCrash(page, sku)

    const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
    expect(await row.getByTestId(`seller-fbs-toggle-${product.id}`).isDisabled(), 'FBS toggle must be disabled with no FBS pool')
    expect((await row.getByTestId(`seller-fbs-status-${product.id}`).innerText()).includes('Нет FBS'), 'No-FBS compact status is not visible')
    evidence.geometry1280 = await row.evaluate((rowElement, productId) => {
      const doc = document.documentElement
      const body = document.body
      const fbsCell = rowElement.querySelector(`[data-testid="seller-fbs-cell-${productId}"]`)
      const table = rowElement.closest('table')
      const container = rowElement.closest('.MuiTableContainer-root')
      return {
        viewportWidth: window.innerWidth,
        documentScrollWidth: doc.scrollWidth,
        bodyScrollWidth: body.scrollWidth,
        rowHeight: rowElement.getBoundingClientRect().height,
        fbsCellText: fbsCell?.textContent ?? '',
        tableScrollWidth: table?.scrollWidth ?? 0,
        tableContainerClientWidth: container?.clientWidth ?? 0,
        tableContainerScrollWidth: container?.scrollWidth ?? 0,
      }
    }, product.id)
    expect(evidence.geometry1280.documentScrollWidth <= evidence.geometry1280.viewportWidth + 1, 'document horizontal overflow at 1280')
    expect(evidence.geometry1280.bodyScrollWidth <= evidence.geometry1280.viewportWidth + 1, 'body horizontal overflow at 1280')
    expect(evidence.geometry1280.tableContainerScrollWidth <= evidence.geometry1280.tableContainerClientWidth + 1, 'table container overflow at 1280')

    await row.getByTestId(`seller-product-select-${product.id}`).click()
    await page.getByTestId('seller-fbs-bulk-action').click()
    await page.getByTestId('seller-fbs-bulk-enable').click()
    await page.getByTestId('seller-fbs-bulk-confirm-dialog').waitFor({ state: 'visible' })
    await page.locator('.MuiMenu-root').waitFor({ state: 'hidden', timeout: 5_000 }).catch(() => {})
    await page.waitForTimeout(500)
    await shot(page, '02-selected-only-confirm-dialog')
    const [bulkRequest] = await Promise.all([
      page.waitForRequest((request) => request.method() === 'PATCH' && request.url().includes('/api/products/fbs-stock-sync/bulk')),
      page.getByTestId('seller-fbs-bulk-confirm-submit').click(),
    ])
    evidence.bulkPatchBody = bulkRequest.postDataJSON()
    expect(JSON.stringify(evidence.bulkPatchBody.product_ids) === JSON.stringify([product.id]), 'Bulk request did not contain selected product_ids only')
    await page.getByTestId('seller-fbs-bulk-result').waitFor({ state: 'visible' })
    await shot(page, '03-bulk-result-visible')

    await row.getByTestId(`seller-stock-directions-toggle-${product.id}`).click()
    const panel = page.getByTestId(`seller-stock-directions-panel-${product.id}`)
    await panel.waitFor({ state: 'visible' })
    await page.getByTestId(`seller-stock-direction-name-${product.id}`).fill('FBS WB')
    await page.getByTestId(`seller-stock-direction-quantity-${product.id}`).fill('3')
    await page.getByTestId(`seller-stock-direction-fbs-${product.id}`).click()
    const [createDirection] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes(`/api/products/${product.id}/stock-directions`) && r.status() === 201),
      page.getByTestId(`seller-stock-direction-submit-${product.id}`).click(),
    ])
    const directionId = (await createDirection.json()).id
    await panel.getByTestId(`seller-stock-direction-row-${directionId}`).waitFor({ state: 'visible' })
    await shot(page, '04-f08-direction-created')

    await page.getByTestId(`seller-stock-direction-edit-${directionId}`).click()
    await page.getByTestId(`seller-stock-direction-quantity-${product.id}`).fill('4')
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes(`/api/products/stock-directions/${directionId}`) && r.status() === 200),
      page.getByTestId(`seller-stock-direction-submit-${product.id}`).click(),
    ])
    expect((await panel.getByTestId(`seller-stock-direction-row-${directionId}`).innerText()).includes('4 шт'), 'Direction edit result is not visible')
    await page.getByTestId(`seller-stock-direction-delete-${directionId}`).click()
    await page.getByTestId('seller-stock-direction-delete-dialog').waitFor({ state: 'visible' })
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes(`/api/products/stock-directions/${directionId}`) && r.status() === 204),
      page.getByTestId('seller-stock-direction-confirm-delete').click(),
    ])
    await panel.getByTestId(`seller-stock-direction-row-${directionId}`).waitFor({
      state: 'detached',
      timeout: 10_000,
    })
    await shot(page, '05-f08-direction-deleted')

    evidence.checks.sellerProductsOpensWithoutCrash = true
    evidence.checks.no1280Overflow = true
    evidence.checks.noChipChaosOrRawStatuses = true
    evidence.checks.selectedOnlyBulkRequest = true
    evidence.checks.noFbsPoolSafe = true
    evidence.checks.f08DrawerCrud = true
    evidence.verdict = 'PASSED'
  } finally {
    await fs.writeFile(path.join(root, 'f23-browser-product-qa-evidence.json'), JSON.stringify(evidence, null, 2))
    await context.close().catch(() => {})
    await browser.close().catch(() => {})
  }
}

async function expectRowNoCrash(page, sku) {
  await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
  await page.getByTestId('seller-product-row').filter({ hasText: sku }).waitFor({ state: 'visible' })
}

main().catch(async (error) => {
  evidence.error = String(error?.stack ?? error)
  await fs.writeFile(path.join(root, 'f23-browser-product-qa-evidence.json'), JSON.stringify(evidence, null, 2))
  console.error(error)
  process.exit(1)
})
