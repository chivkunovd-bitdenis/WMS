import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const require = createRequire('/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend/package.json')
const { chromium, expect } = require('@playwright/test')

const API = process.env.F22_API_ORIGIN ?? 'http://127.0.0.1:18122'
const WEB = process.env.F22_WEB_ORIGIN ?? 'http://127.0.0.1:15182'
const EMU = process.env.F22_EMULATOR_ORIGIN ?? 'http://127.0.0.1:18123'
const OUT = process.env.F22_EVIDENCE_DIR ?? process.cwd()
const WMS_DB_PATH = process.env.F22_WMS_DB_PATH

const WB_TOKEN = 'f22-safe-token'
const WB_WAREHOUSE_ID = 501001
const CHRT_ID = 111001
const WB_BARCODE = 'F22-WB-BARCODE'
const WB_NM_ID = 22022022

const evidence = {
  status: 'BROWSER_PRODUCT_QA_FAILED',
  checks: [],
  commands: {
    runner: 'docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/run_f22_browser_product_qa_final.sh',
  },
}

function record(name, passed, details = {}) {
  evidence.checks.push({ name, passed, ...details })
  if (!passed) {
    evidence.status = 'BROWSER_PRODUCT_QA_FAILED'
  }
}

async function api(pathname, { method = 'GET', token, body, ok = true } = {}) {
  const res = await fetch(`${API}${pathname}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  let json = null
  if (text) {
    try {
      json = JSON.parse(text)
    } catch {
      json = text
    }
  }
  if (ok && !res.ok) {
    throw new Error(`${method} ${pathname} -> ${res.status}: ${text}`)
  }
  return { res, json, text }
}

async function emulatorStock() {
  const res = await fetch(`${EMU}/api/v3/stocks/${WB_WAREHOUSE_ID}`, {
    method: 'POST',
    headers: { Authorization: WB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ chrtIds: [CHRT_ID] }),
  })
  if (!res.ok) {
    throw new Error(`emulator read stock -> ${res.status}: ${await res.text()}`)
  }
  const body = await res.json()
  const row = (body.stocks ?? []).find((item) => Number(item.chrtId) === CHRT_ID)
  return row ? Number(row.amount) : 0
}

async function setEmulatorStock(amount) {
  const res = await fetch(`${EMU}/api/v3/stocks/${WB_WAREHOUSE_ID}`, {
    method: 'PUT',
    headers: { Authorization: WB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ stocks: [{ chrtId: CHRT_ID, amount }] }),
  })
  if (res.status !== 204) {
    throw new Error(`emulator put stock -> ${res.status}: ${await res.text()}`)
  }
}

async function poll(fn, predicate, timeoutMs = 15000) {
  const started = Date.now()
  let last
  while (Date.now() - started < timeoutMs) {
    last = await fn()
    if (predicate(last)) return last
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`poll timeout, last=${JSON.stringify(last)}`)
}

async function loginSeller(page, email, password) {
  await page.goto(`${WEB}/seller/`)
  await expect(page.getByTestId('login-form')).toBeVisible()
  await page.getByTestId('login-form').getByLabel('Email').fill(email)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/login') && r.status() === 200),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])
  await expect(page.getByTestId('app-frame')).toBeVisible()
}

async function seedInbound({ adminToken, warehouseId, productId }) {
  const loc = await api(`/warehouses/${warehouseId}/locations`, {
    method: 'POST',
    token: adminToken,
    body: { code: `F22-CELL-${Date.now()}` },
  })
  const locationId = loc.json.id
  const inbound = await api('/operations/inbound-intake-requests', {
    method: 'POST',
    token: adminToken,
    body: { warehouse_id: warehouseId },
  })
  const inboundId = inbound.json.id
  await api(`/operations/inbound-intake-requests/${inboundId}/lines`, {
    method: 'POST',
    token: adminToken,
    body: { product_id: productId, expected_qty: 7, storage_location_id: locationId },
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/submit`, {
    method: 'POST',
    token: adminToken,
  })
  const got = await api(`/operations/inbound-intake-requests/${inboundId}`, { token: adminToken })
  const lineId = got.json.lines[0].id
  await api(`/operations/inbound-intake-requests/${inboundId}/lines/${lineId}/actual`, {
    method: 'PATCH',
    token: adminToken,
    body: { actual_qty: 0 },
  })
  const box = await api(`/operations/inbound-intake-requests/${inboundId}/boxes`, {
    method: 'POST',
    token: adminToken,
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/boxes/open`, {
    method: 'POST',
    token: adminToken,
    body: { barcode: box.json.internal_barcode },
  })
  for (let i = 0; i < 7; i += 1) {
    await api(`/operations/inbound-intake-requests/${inboundId}/boxes/${box.json.id}/scan`, {
      method: 'POST',
      token: adminToken,
      body: { barcode: WB_BARCODE },
    })
  }
  await api(`/operations/inbound-intake-requests/${inboundId}/boxes/${box.json.id}/close`, {
    method: 'POST',
    token: adminToken,
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/verify`, {
    method: 'POST',
    token: adminToken,
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/post`, {
    method: 'POST',
    token: adminToken,
  })
}

function forceWbLinkInLocalQaDb(productId) {
  if (!WMS_DB_PATH) {
    throw new Error('F22_WMS_DB_PATH is required for local WB link fixture')
  }
  const productIdHex = productId.replaceAll('-', '')
  const code = `
import sqlite3
db = sqlite3.connect(${JSON.stringify(WMS_DB_PATH)})
updated = db.execute(
  "update products set wb_nm_id = ?, wb_chrt_id = ?, wb_barcode = ? where id = ?",
  (${WB_NM_ID}, ${CHRT_ID}, ${JSON.stringify(WB_BARCODE)}, ${JSON.stringify(productId)}),
).rowcount
if updated == 0:
    updated = db.execute(
      "update products set wb_nm_id = ?, wb_chrt_id = ?, wb_barcode = ? where id = ?",
      (${WB_NM_ID}, ${CHRT_ID}, ${JSON.stringify(WB_BARCODE)}, ${JSON.stringify(productIdHex)}),
    ).rowcount
if updated != 1:
    raise RuntimeError(f"expected one product WB-link update, got {updated}")
db.commit()
db.close()
`
  execFileSync('/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/backend/.venv/bin/python', ['-c', code], {
    cwd: '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812',
    stdio: 'pipe',
  })
}

function readBindingLeaseUntil() {
  if (!WMS_DB_PATH) {
    throw new Error('F22_WMS_DB_PATH is required for local lease readback')
  }
  const code = `
import json
import sqlite3
db = sqlite3.connect(${JSON.stringify(WMS_DB_PATH)})
row = db.execute("select lease_until from fbs_warehouse_bindings where wb_warehouse_id = ?", (${WB_WAREHOUSE_ID},)).fetchone()
db.close()
print(json.dumps(row[0] if row else None))
`
  const out = execFileSync('/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/backend/.venv/bin/python', ['-c', code], {
    cwd: '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812',
    stdio: 'pipe',
    encoding: 'utf8',
  })
  return JSON.parse(out)
}

async function main() {
  evidence.status = 'BROWSER_PRODUCT_QA_PASSED'
  const suffix = Date.now()
  const adminEmail = `f22-admin-${suffix}@example.com`
  const sellerEmail = `f22-seller-${suffix}@example.com`
  const password = 'password123'
  const sku = `F22-SAFE-${suffix}`

  const reg = await api('/auth/register', {
    method: 'POST',
    body: {
      organization_name: `F22 QA ${suffix}`,
      slug: `f22-qa-${suffix}`,
      admin_email: adminEmail,
      password,
    },
  })
  const adminToken = reg.json.access_token
  const seller = await api('/sellers', {
    method: 'POST',
    token: adminToken,
    body: { name: `F22 Seller ${suffix}` },
  })
  const sellerId = seller.json.id
  const warehouse = await api('/warehouses', {
    method: 'POST',
    token: adminToken,
    body: { name: 'F22 FBS warehouse', code: `f22-wh-${suffix}` },
  })
  const warehouseId = warehouse.json.id
  await api(`/integrations/wildberries/sellers/${sellerId}/tokens`, {
    method: 'PATCH',
    token: adminToken,
    body: { marketplace_api_token: WB_TOKEN },
  })
  await api(`/operations/fbs-sellers/${sellerId}/warehouse-bindings/${WB_WAREHOUSE_ID}`, {
    method: 'PUT',
    token: adminToken,
    body: { wms_warehouse_id: warehouseId, stock_sync_enabled: true },
  })
  await api('/auth/seller-accounts', {
    method: 'POST',
    token: adminToken,
    body: { seller_id: sellerId, email: sellerEmail, password },
  })
  const product = await api('/products', {
    method: 'POST',
    token: adminToken,
    body: {
      name: 'F22 Safe Sync Product',
      sku_code: sku,
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
      seller_id: sellerId,
      wb_barcode: WB_BARCODE,
    },
  })
  const productId = product.json.id
  forceWbLinkInLocalQaDb(productId)

  await setEmulatorStock(20)

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } })
  const requests = []
  page.on('request', (req) => {
    const url = req.url()
    if (url.includes('/fbs-stock-sync') || url.includes('/stocks/sync')) {
      requests.push({ method: req.method(), url })
    }
  })

  await loginSeller(page, sellerEmail, password)
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible()
  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  const headerText = await page.getByTestId('seller-products-table').locator('thead').innerText()
  const pageTextBefore = await page.locator('body').innerText()
  const rowScreenshot = path.join(OUT, 'seller-products-no-fbs-pool.png')
  await page.screenshot({ path: rowScreenshot, fullPage: true })

  const statusBefore = await row.getByTestId(`seller-fbs-status-${productId}`).innerText()
  const toggleEnabled = await row.getByTestId(`seller-fbs-toggle-${productId}`).isEnabled()
  await row.getByTestId(`seller-fbs-toggle-${productId}`).click({ force: true }).catch(() => undefined)
  await page.waitForTimeout(1000)
  const stockAfterDisabledAttempt = await emulatorStock()

  record('seller UI blocks missing FBS pool from sending zero', !toggleEnabled && stockAfterDisabledAttempt === 20, {
    statusBefore,
    toggleEnabled,
    stockBefore: 20,
    stockAfterDisabledAttempt,
    matchingRequests: requests,
  })
  record('seller products header has no Limit column', !/Лимит/.test(headerText), { headerText })
  record('seller products screen has no raw technical errors', !/(unsafe_stock_unknown|unsafe_zero_blocked|warehouse_mapping_missing|pending_confirmation|stack trace|undefined|null)/i.test(pageTextBefore), {
    matchedTextSample: pageTextBefore.slice(0, 2000),
  })
  const layout = await page.evaluate(() => ({
    innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    blackStrip: getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)',
  }))
  record('1280px layout has no horizontal page overflow or black strip', layout.scrollWidth <= layout.innerWidth && layout.bodyScrollWidth <= layout.innerWidth && !layout.blackStrip, layout)

  await api(`/products/${productId}/fbs-stock-sync`, {
    method: 'PATCH',
    token: adminToken,
    body: { fbs_stock_sync_enabled: true },
  })
  const noPoolSync = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync`, {
    method: 'POST',
    token: adminToken,
    body: { wb_warehouse_id: WB_WAREHOUSE_ID },
  })
  const unsafeState = await poll(async () => {
    const amount = await emulatorStock()
    const status = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync-status?wb_warehouse_id=${WB_WAREHOUSE_ID}`, {
      token: adminToken,
    })
    const item = status.json.items.find((row) => Number(row.chrt_id) === CHRT_ID)
    return { amount, item, leaseUntil: readBindingLeaseUntil() }
  }, (state) => state.amount === 20 && state.item?.status === 'error' && state.leaseUntil === null, 15000)
  record('backend scheduled enable with missing pool keeps WB at 20', unsafeState.amount === 20 && unsafeState.item?.status === 'error', {
    emulatorAmount: unsafeState.amount,
    syncItem: unsafeState.item,
    syncResult: noPoolSync.json,
  })
  await api(`/products/${productId}/fbs-stock-sync`, {
    method: 'PATCH',
    token: adminToken,
    body: { fbs_stock_sync_enabled: false },
  })

  await seedInbound({ adminToken, warehouseId, productId })
  await page.goto(`${WEB}/seller/`)
  await expect(page.getByTestId('app-frame')).toBeVisible({ timeout: 20000 })
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible({ timeout: 20000 })
  const rowAfterStock = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(rowAfterStock).toBeVisible()
  await rowAfterStock.getByTestId(`seller-stock-directions-toggle-${productId}`).click()
  await expect(page.getByTestId(`seller-stock-directions-panel-${productId}`)).toBeVisible()
  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('FBS QA pool')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('7')
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).check()
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/products/${productId}/stock-directions`) && r.request().method() === 'POST' && r.ok()),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await page.getByRole('button', { name: 'Закрыть' }).click()
  await expect(rowAfterStock.getByTestId(`seller-fbs-status-${productId}`)).toContainText('Пауза')
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/products/${productId}/fbs-stock-sync`) && r.request().method() === 'PATCH' && r.ok()),
    rowAfterStock.getByTestId(`seller-fbs-toggle-${productId}`).click(),
  ])
  await expect(rowAfterStock.getByTestId(`seller-fbs-status-${productId}`)).toContainText(/Проверяем WB|Ошибка WB|WB:/)
  const positiveSync = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync`, {
    method: 'POST',
    token: adminToken,
    body: { wb_warehouse_id: WB_WAREHOUSE_ID },
  })
  await poll(emulatorStock, (amount) => amount === 7, 15000)
  const confirmedState = await poll(async () => {
    const status = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync-status?wb_warehouse_id=${WB_WAREHOUSE_ID}`, {
      token: adminToken,
    })
    return status.json.items.find((item) => Number(item.chrt_id) === CHRT_ID)
  }, (item) => item?.status === 'confirmed' && Number(item?.confirmed) === 7, 15000)
  await page.goto(`${WEB}/seller/`)
  await expect(page.getByTestId('app-frame')).toBeVisible({ timeout: 20000 })
  await page.getByTestId('nav-seller-products').click()
  await expect(page.getByTestId('seller-products-table')).toBeVisible({ timeout: 20000 })
  const positiveRow = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await expect(positiveRow.getByTestId(`seller-fbs-status-${productId}`)).toContainText(/WB: 7 шт|Проверяем WB/, { timeout: 20000 })
  const positiveStatus = await positiveRow.getByTestId(`seller-fbs-status-${productId}`).innerText()
  const positiveScreenshot = path.join(OUT, 'seller-products-fbs-pool-7.png')
  await page.screenshot({ path: positiveScreenshot, fullPage: true })
  const syncStatusAfterPositive = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync-status?wb_warehouse_id=${WB_WAREHOUSE_ID}`, {
    token: adminToken,
  })
  const positiveItem = syncStatusAfterPositive.json.items.find((item) => Number(item.chrt_id) === CHRT_ID) ?? confirmedState
  const finalStock = await emulatorStock()
  record('positive FBS pool publishes 7 only after readback', positiveSync.json.bindings_processed === 1 && positiveSync.json.products_confirmed === 1 && finalStock === 7 && positiveItem?.status === 'confirmed' && Number(positiveItem?.confirmed) === 7, {
    emulatorAmount: finalStock,
    syncItem: positiveItem,
    syncResult: positiveSync.json,
  })
  record('seller UI shows compact confirmed/pending-safe state after positive sync', /WB: 7 шт|Проверяем WB/.test(positiveStatus), {
    positiveStatus,
  })

  await browser.close()
}

try {
  await main()
} catch (error) {
  evidence.status = 'BROWSER_PRODUCT_QA_FAILED'
  evidence.error = error instanceof Error ? { message: error.message, stack: error.stack } : String(error)
  console.error(error)
  process.exitCode = 1
} finally {
  writeFileSync(path.join(OUT, 'f22-browser-product-qa-result.json'), JSON.stringify(evidence, null, 2))
  console.log(JSON.stringify(evidence, null, 2))
}
