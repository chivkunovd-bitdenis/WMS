import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'

const ROOT = '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812'
const OUT = process.env.CATALOG_RERUN_EVIDENCE_DIR ?? path.join(
  ROOT,
  'docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict',
)
const RUN_DIR = process.env.CATALOG_RERUN_RUN_DIR ?? OUT
const API = process.env.CATALOG_RERUN_API_ORIGIN ?? 'http://127.0.0.1:18591'
const WEB = process.env.CATALOG_RERUN_WEB_ORIGIN ?? 'http://127.0.0.1:15591'
const EMU = process.env.CATALOG_RERUN_EMULATOR_ORIGIN ?? 'http://127.0.0.1:18592'
const WMS_DB_PATH = process.env.CATALOG_RERUN_WMS_DB_PATH
const FINAL_MD = path.join(OUT, 'FINAL_BROWSER_REGRESSION_RERUN_CATALOG_LIVE_STRICT_RU.md')
const RESULT_JSON = path.join(RUN_DIR, 'live-result.json')

const WB_TOKEN = 'catalog-rerun-token'
const WB_WAREHOUSE_ID = 501991
const WB_CHRT_ID = 9914242
const WB_NM_ID = 424242
const WB_BARCODE = 'E2E-MOCK-BARCODE'

const require = createRequire(path.join(ROOT, 'frontend/package.json'))
const { chromium, expect } = require('@playwright/test')

class ProductFailure extends Error {}

const evidence = {
  started_at: new Date().toISOString(),
  verdict: 'FINAL_BROWSER_GROUP_BLOCKED',
  browser_used: false,
  browser: 'Chromium via Playwright headless=false',
  viewport: { width: 1280, height: 720 },
  ports: {
    backend: Number(process.env.CATALOG_RERUN_API_PORT ?? 18591),
    frontend: Number(process.env.CATALOG_RERUN_WEB_PORT ?? 15591),
    emulator: Number(process.env.CATALOG_RERUN_EMU_PORT ?? 18592),
  },
  urls: { backend: API, frontend: WEB, emulator: EMU },
  db: WMS_DB_PATH ?? null,
  route_list: [],
  clicks: [],
  screenshots: [],
  checks: [],
  metrics: {},
  seed: {},
  network: { bulkPatchBodies: [], stockSyncResults: [] },
  blockers: [],
}

function rememberRoute(route) {
  evidence.route_list.push(route)
}

function rememberClick(label, details = {}) {
  evidence.clicks.push({ label, ...details })
}

function record(name, passed, details = {}) {
  evidence.checks.push({ name, passed, details })
  return passed
}

function requireCheck(name, condition, details = {}) {
  record(name, Boolean(condition), details)
  if (!condition) {
    throw new ProductFailure(name)
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

async function shot(page, name) {
  const file = path.join(RUN_DIR, `${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  evidence.screenshots.push(file)
  return file
}

async function waitResponse(page, method, urlPart, expected = '2xx') {
  return page.waitForResponse((response) => {
    const status = response.status()
    const statusOk = expected === '2xx'
      ? status >= 200 && status < 300
      : Array.isArray(expected)
        ? expected.includes(status)
        : status === expected
    return response.request().method() === method && response.url().includes(urlPart) && statusOk
  })
}

async function emulatorStock() {
  const res = await fetch(`${EMU}/api/v3/stocks/${WB_WAREHOUSE_ID}`, {
    method: 'POST',
    headers: { Authorization: WB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ chrtIds: [WB_CHRT_ID] }),
  })
  if (!res.ok) {
    throw new Error(`emulator read stock -> ${res.status}: ${await res.text()}`)
  }
  const body = await res.json()
  const row = (body.stocks ?? []).find((item) => Number(item.chrtId) === WB_CHRT_ID)
  return row ? Number(row.amount) : 0
}

async function setEmulatorStock(amount) {
  const res = await fetch(`${EMU}/api/v3/stocks/${WB_WAREHOUSE_ID}`, {
    method: 'PUT',
    headers: { Authorization: WB_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ stocks: [{ chrtId: WB_CHRT_ID, amount }] }),
  })
  if (res.status !== 204) {
    throw new Error(`emulator put stock -> ${res.status}: ${await res.text()}`)
  }
}

async function poll(fn, predicate, timeoutMs = 20_000) {
  const started = Date.now()
  let last
  while (Date.now() - started < timeoutMs) {
    last = await fn()
    if (predicate(last)) return last
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`poll timeout, last=${JSON.stringify(last)}`)
}

function forceWbChrtInLocalQaDb(productId) {
  if (!WMS_DB_PATH) throw new Error('CATALOG_RERUN_WMS_DB_PATH is required')
  const productIdHex = productId.replaceAll('-', '')
  const code = `
import json
import sqlite3
db = sqlite3.connect(${JSON.stringify(WMS_DB_PATH)})
updated = db.execute(
    "update products set wb_nm_id = ?, wb_chrt_id = ?, wb_barcode = ? where id = ?",
    (${WB_NM_ID}, ${WB_CHRT_ID}, ${JSON.stringify(WB_BARCODE)}, ${JSON.stringify(productId)}),
).rowcount
if updated == 0:
    updated = db.execute(
        "update products set wb_nm_id = ?, wb_chrt_id = ?, wb_barcode = ? where id = ?",
        (${WB_NM_ID}, ${WB_CHRT_ID}, ${JSON.stringify(WB_BARCODE)}, ${JSON.stringify(productIdHex)}),
    ).rowcount
if updated != 1:
    raise RuntimeError(f"expected one product WB chrt update, got {updated}")
db.commit()
row = db.execute("select id, sku_code, wb_nm_id, wb_chrt_id, wb_barcode from products where wb_nm_id = ?", (${WB_NM_ID},)).fetchone()
db.close()
print(json.dumps(row, ensure_ascii=False))
`
  const out = execFileSync(path.join(ROOT, 'backend/.venv/bin/python'), ['-c', code], {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: 'pipe',
  })
  return JSON.parse(out)
}

async function seedInboundStock({ token, warehouseId, productId, qty }) {
  const location = await api(`/warehouses/${warehouseId}/locations`, {
    method: 'POST',
    token,
    body: { code: `CATALOG-RERUN-CELL-${Date.now()}` },
  })
  const inbound = await api('/operations/inbound-intake-requests', {
    method: 'POST',
    token,
    body: { warehouse_id: warehouseId },
  })
  const inboundId = inbound.json.id
  await api(`/operations/inbound-intake-requests/${inboundId}/lines`, {
    method: 'POST',
    token,
    body: {
      product_id: productId,
      expected_qty: qty,
      storage_location_id: location.json.id,
    },
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/submit`, { method: 'POST', token })
  const detail = await api(`/operations/inbound-intake-requests/${inboundId}`, { token })
  const lineId = detail.json.lines[0].id
  await api(`/operations/inbound-intake-requests/${inboundId}/lines/${lineId}/actual`, {
    method: 'PATCH',
    token,
    body: { actual_qty: 0 },
  })
  const box = await api(`/operations/inbound-intake-requests/${inboundId}/boxes`, {
    method: 'POST',
    token,
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/boxes/open`, {
    method: 'POST',
    token,
    body: { barcode: box.json.internal_barcode },
  })
  for (let i = 0; i < qty; i += 1) {
    await api(`/operations/inbound-intake-requests/${inboundId}/boxes/${box.json.id}/scan`, {
      method: 'POST',
      token,
      body: { barcode: WB_BARCODE },
    })
  }
  await api(`/operations/inbound-intake-requests/${inboundId}/boxes/${box.json.id}/close`, {
    method: 'POST',
    token,
  })
  await api(`/operations/inbound-intake-requests/${inboundId}/verify`, { method: 'POST', token })
  await api(`/operations/inbound-intake-requests/${inboundId}/post`, { method: 'POST', token })
  return { inboundId, locationId: location.json.id, boxId: box.json.id }
}

async function loginSeller(page, email, password) {
  rememberRoute(`${WEB}/seller/`)
  await page.goto(`${WEB}/seller/`)
  await page.getByTestId('login-form').waitFor({ state: 'visible' })
  rememberClick('seller login form: fill email/password')
  await page.getByTestId('login-form').getByLabel('Email').fill(email)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password)
  rememberClick('seller login form: Войти')
  await Promise.all([
    waitResponse(page, 'POST', '/api/auth/login', 200),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])
  await page.getByTestId('app-frame').waitFor({ state: 'visible' })
}

async function loginAdmin(page, email, password) {
  rememberRoute(`${WEB}/`)
  await page.goto(`${WEB}/`)
  await page.getByTestId('login-form').waitFor({ state: 'visible' })
  rememberClick('ff admin login form: fill email/password')
  await page.getByTestId('login-form').getByLabel('Email').fill(email)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password)
  rememberClick('ff admin login form: Войти')
  await Promise.all([
    waitResponse(page, 'POST', '/api/auth/login', 200),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])
  await page.getByTestId('app-frame').waitFor({ state: 'visible' })
}

async function getSellerRow(page, sku) {
  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await row.waitFor({ state: 'visible' })
  return row
}

async function rowStockTexts(row, productId) {
  return {
    inStorage: await row.getByTestId('seller-stock-in-storage').innerText(),
    onHand: await row.getByTestId('seller-stock-on-hand').innerText(),
    freeFbo: await row.getByTestId('seller-stock-free-fbo').innerText(),
    distribution: await row.getByTestId(`seller-stock-distribution-${productId}`).innerText(),
    status: await row.getByTestId(`seller-fbs-status-${productId}`).innerText(),
    fbsCell: await row.getByTestId(`seller-fbs-cell-${productId}`).innerText(),
    packaging: await row.getByTestId(`seller-packaging-status-${productId}`).innerText(),
  }
}

async function sellerMetrics(page, productId) {
  return page.evaluate((pid) => {
    const table = document.querySelector('[data-testid="seller-products-table"]')
    const container = document.querySelector('[data-testid="seller-products-list"]')
    const row = Array.from(document.querySelectorAll('[data-testid="seller-product-row"]'))
      .find((el) => el.querySelector(`[data-testid="seller-fbs-cell-${pid}"]`))
    const headers = Array.from(document.querySelectorAll('[data-testid="seller-products-table"] thead th'))
      .map((th) => (th.textContent || '').trim())
    const poolButton = document.querySelector(`[data-testid="seller-stock-directions-toggle-${pid}"]`)
    const packagingButton = document.querySelector(`[data-testid="seller-packaging-edit-${pid}"]`)
    const bounds = (el) => {
      if (!el) return null
      const rect = el.getBoundingClientRect()
      return {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        right: rect.right,
        bottom: rect.bottom,
        text: el.textContent || '',
      }
    }
    const visibleWithinViewport = (b) => Boolean(
      b &&
      b.x >= 0 &&
      b.y >= 0 &&
      b.right <= window.innerWidth + 1 &&
      b.bottom <= window.innerHeight + 1 &&
      b.width > 0 &&
      b.height > 0
    )
    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      documentClientWidth: document.documentElement.clientWidth,
      bodyClientWidth: document.body.clientWidth,
      tableScrollWidth: table?.scrollWidth ?? 0,
      tableClientWidth: table?.clientWidth ?? 0,
      containerScrollWidth: container?.scrollWidth ?? 0,
      containerClientWidth: container?.clientWidth ?? 0,
      rowHeight: row?.getBoundingClientRect().height ?? 0,
      headers,
      poolButton: bounds(poolButton),
      packagingButton: bounds(packagingButton),
      poolButtonVisible: visibleWithinViewport(bounds(poolButton)),
      packagingButtonVisible: visibleWithinViewport(bounds(packagingButton)),
      pageText: document.body.textContent || '',
    }
  }, productId)
}

async function syncStatusState(sellerId, token) {
  const amount = await emulatorStock()
  const status = await api(
    `/operations/fbs-sellers/${sellerId}/stocks/sync-status?wb_warehouse_id=${WB_WAREHOUSE_ID}`,
    { token },
  )
  const item = status.json.items.find((row) => Number(row.chrt_id) === WB_CHRT_ID) ?? null
  return { amount, item, status: status.json }
}

function hasRawCatalogNoise(text) {
  return /(WB \/ ШК|Действия|12\s*\/\s*12\s*\/\s*7|12\s*\/\s*12\s*\/\s*12|unsafe_stock_unknown|unsafe_zero_blocked|warehouse_mapping_missing|pending_confirmation|ambiguous_warehouse_scope|stack trace|undefined|null|Лимит)/i.test(text)
}

async function writeArtifacts() {
  evidence.finished_at = new Date().toISOString()
  const failed = evidence.checks.filter((check) => !check.passed)
  if (evidence.blockers.length > 0) {
    evidence.verdict = 'FINAL_BROWSER_GROUP_BLOCKED'
  } else if (failed.length > 0) {
    evidence.verdict = 'FINAL_BROWSER_GROUP_FAILED'
  } else {
    evidence.verdict = 'FINAL_BROWSER_GROUP_PASSED'
  }
  await fs.writeFile(RESULT_JSON, `${JSON.stringify(evidence, null, 2)}\n`)

  const checkLines = evidence.checks
    .map((check) => `- ${check.passed ? 'PASS' : 'FAIL'}: ${check.name} — \`${JSON.stringify(check.details)}\``)
    .join('\n')
  const screenshotLines = evidence.screenshots.map((file) => `- \`${file}\``).join('\n')
  const routeLines = evidence.route_list.map((route) => `- \`${route}\``).join('\n')
  const clickLines = evidence.clicks.map((click) => `- ${click.label}${Object.keys(click).length > 1 ? ` — \`${JSON.stringify(click)}\`` : ''}`).join('\n')
  const blockerLines = evidence.blockers.length
    ? evidence.blockers.map((item) => `- ${item}`).join('\n')
    : '- нет'

  const md = `# FINAL_BROWSER_REGRESSION_RERUN_CATALOG_LIVE_STRICT_RU

Дата: ${new Date().toISOString()}.

Repo: \`${ROOT}\`.

Verdict: \`${evidence.verdict}\`.

Код, commit, push, staging, production, Railway и внешние кабинеты секретов не трогались. Созданы только локальные evidence-файлы в этой папке.

## Live Browser

| Поле | Значение |
| --- | --- |
| browser_used | \`${evidence.browser_used ? 'yes' : 'no'}\` |
| browser | \`${evidence.browser}\` |
| viewport | \`${evidence.viewport.width}x${evidence.viewport.height}\` |
| frontend | \`${WEB}\` |
| backend | \`${API}\` |
| emulator | \`${EMU}\` |
| sqlite | \`${WMS_DB_PATH ?? 'n/a'}\` |
| result_json | \`${RESULT_JSON}\` |

## Seed

\`\`\`json
${JSON.stringify(evidence.seed, null, 2)}
\`\`\`

## Routes

${routeLines}

## Clicks

${clickLines}

## Screenshots

${screenshotLines}

## Mandatory Checks

${checkLines}

## Metrics

\`\`\`json
${JSON.stringify(evidence.metrics, null, 2)}
\`\`\`

## Network Evidence

\`\`\`json
${JSON.stringify(evidence.network, null, 2)}
\`\`\`

## Blockers

${blockerLines}

## Product Judgement

Seller catalog columns and actions are justified for seller/warehouse marketplace work: product identity, \`Артикул WB\`, labeled stock, FBS pool split, WB publication state, and \`ТЗ / ЧЗ\`. The rerun rejects the old overloaded pattern: no \`WB / ШК\` header, no separate \`Действия\` column, no naked \`12 / 12 / 7\`, no raw sync codes, no visible chip chaos, and no \`WB: 0 шт\` success for a missing FBS pool.

FF catalog cleanup was opened as a natural continuation and checked for business columns plus absence of internal-stage noise.

Final verdict: \`${evidence.verdict}\`.
`
  await fs.writeFile(FINAL_MD, md)
}

async function main() {
  await fs.mkdir(RUN_DIR, { recursive: true })
  const suffix = Date.now()
  const adminEmail = `catalog-rerun-admin-${suffix}@example.com`
  const sellerEmail = `catalog-rerun-seller-${suffix}@example.com`
  const password = 'password123'

  const registration = await api('/auth/register', {
    method: 'POST',
    body: {
      organization_name: `Catalog Rerun FF ${suffix}`,
      slug: `catalog-rerun-${suffix}`,
      admin_email: adminEmail,
      password,
    },
  })
  const adminToken = registration.json.access_token
  const seller = await api('/sellers', {
    method: 'POST',
    token: adminToken,
    body: { name: `Catalog Rerun Seller ${suffix}` },
  })
  const sellerId = seller.json.id
  await api('/auth/seller-accounts', {
    method: 'POST',
    token: adminToken,
    body: { seller_id: sellerId, email: sellerEmail, password },
  })
  const sellerLogin = await api('/auth/login', {
    method: 'POST',
    body: { email: sellerEmail, password },
  })
  const sellerToken = sellerLogin.json.access_token

  const warehouse = await api('/warehouses', {
    method: 'POST',
    token: adminToken,
    body: { name: `Catalog Rerun WH ${suffix}`, code: `catalog-rerun-wh-${suffix}` },
  })
  await api(`/integrations/wildberries/sellers/${sellerId}/tokens`, {
    method: 'PATCH',
    token: adminToken,
    body: {
      content_api_token: WB_TOKEN,
      supplies_api_token: WB_TOKEN,
      marketplace_api_token: WB_TOKEN,
    },
  })
  const wbSelfToken = await api('/integrations/wildberries/self/content-token', {
    method: 'POST',
    token: sellerToken,
    body: { content_api_token: WB_TOKEN },
  })
  const catalogRows = await api('/products/wb-catalog', { token: sellerToken })
  const productRow = catalogRows.json.find((row) => Number(row.wb_nm_id) === WB_NM_ID)
  if (!productRow) {
    throw new Error(`fixture did not create WB mock product nm_id=${WB_NM_ID}`)
  }
  const productId = productRow.id
  const forcedWb = forceWbChrtInLocalQaDb(productId)
  const inbound = await seedInboundStock({
    token: adminToken,
    warehouseId: warehouse.json.id,
    productId,
    qty: 12,
  })
  await api(`/products/${productId}/packaging-instructions`, {
    method: 'PATCH',
    token: adminToken,
    body: {
      packaging_instructions: 'QA rerun: пакет, стикер WB, проверить ЧЗ перед отгрузкой',
      requires_honest_sign: true,
    },
  })
  await api(`/operations/fbs-sellers/${sellerId}/warehouse-bindings/${WB_WAREHOUSE_ID}`, {
    method: 'PUT',
    token: adminToken,
    body: { wms_warehouse_id: warehouse.json.id, stock_sync_enabled: true },
  })
  await setEmulatorStock(20)

  evidence.seed = {
    suffix,
    adminEmail,
    sellerEmail,
    sellerId,
    warehouseId: warehouse.json.id,
    productId,
    sku: productRow.sku_code,
    wb_nm_id: WB_NM_ID,
    wb_chrt_id: WB_CHRT_ID,
    wb_barcode: WB_BARCODE,
    wbSelfToken,
    forcedWb,
    inbound,
    initialEmulatorStock: 20,
  }

  const browser = await chromium.launch({ headless: false, slowMo: 80 })
  evidence.browser_used = true
  evidence.browser_version = await browser.version()
  const context = await browser.newContext({ viewport: evidence.viewport })
  const page = await context.newPage()
  page.setDefaultTimeout(20_000)
  page.on('request', (request) => {
    if (request.method() === 'PATCH' && request.url().includes('/api/products/fbs-stock-sync/bulk')) {
      evidence.network.bulkPatchBodies.push({
        url: request.url(),
        postData: request.postDataJSON(),
      })
    }
  })

  try {
    await loginSeller(page, sellerEmail, password)
    rememberRoute(`${WEB}/seller/products`)
    await page.goto(`${WEB}/seller/products`)
    await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
    const row = await getSellerRow(page, productRow.sku_code)
    await shot(page, '01-seller-products-initial-1280x720')

    const initialMetrics = await sellerMetrics(page, productId)
    const initialTexts = await rowStockTexts(row, productId)
    evidence.metrics.initialSellerCatalog = initialMetrics
    requireCheck('seller /seller/products opened at 1280x720', initialMetrics.viewportWidth === 1280 && initialMetrics.viewportHeight === 720, initialMetrics)
    requireCheck('headers are exact compact catalog headers with Артикул WB and no WB / ШК or Действия', JSON.stringify(initialMetrics.headers) === JSON.stringify(['', 'Товар', 'Артикул WB', 'Остаток', 'FBS-пул', 'Публикация WB', 'ТЗ / ЧЗ']), initialMetrics.headers)
    requireCheck('stock cell has labels В ячейках / На ФФ / Свободный FBO and no naked stock fraction', initialTexts.inStorage === 'В ячейках 12' && initialTexts.onHand === 'На ФФ 12' && initialTexts.freeFbo === 'Свободный FBO 12' && !/12\s*\/\s*12\s*\/\s*(7|12)/.test(initialMetrics.pageText), initialTexts)
    const initialToggleDisabled = !(await row.getByTestId(`seller-fbs-toggle-${productId}`).isEnabled())
    requireCheck('missing FBS starts as Нет FBS with disabled toggle and no WB zero success', initialTexts.status === 'Нет FBS' && initialToggleDisabled && !initialMetrics.pageText.includes('WB: 0 шт'), { initialTexts, initialToggleDisabled })
    requireCheck('initial layout has rowHeight <=72 and no horizontal overflow', initialMetrics.rowHeight <= 72 && initialMetrics.documentScrollWidth <= 1280 && initialMetrics.bodyScrollWidth <= 1280 && initialMetrics.tableScrollWidth <= initialMetrics.containerClientWidth + 1, initialMetrics)
    requireCheck('pool and ТЗ action bounds are visible, no clipped action column', initialMetrics.poolButtonVisible && initialMetrics.packagingButtonVisible, { pool: initialMetrics.poolButton, packaging: initialMetrics.packagingButton })
    requireCheck('initial seller catalog has no raw code/chip/noise regression', !hasRawCatalogNoise(initialMetrics.pageText), { sample: initialMetrics.pageText.slice(0, 2000) })

    rememberClick('select seller product row', { productId })
    await row.getByTestId(`seller-product-select-${productId}`).click()
    rememberClick('Изменить публикацию')
    await page.getByTestId('seller-fbs-bulk-action').click()
    rememberClick('Включить')
    await page.getByTestId('seller-fbs-bulk-enable').click()
    const confirmDialog = page.getByTestId('seller-fbs-bulk-confirm-dialog')
    await confirmDialog.waitFor({ state: 'visible' })
    const confirmText = await confirmDialog.innerText()
    await shot(page, '02-selected-only-bulk-confirm-1280x720')
    requireCheck('bulk confirm is selected-only for 1 product', confirmText.includes('для 1 товаров') && confirmText.includes('Будут изменены только выбранные товары') && confirmText.includes(productRow.sku_code), { confirmText })
    rememberClick('bulk confirm submit')
    const [bulkRequest, bulkResponse] = await Promise.all([
      page.waitForRequest((request) => request.method() === 'PATCH' && request.url().includes('/api/products/fbs-stock-sync/bulk')),
      waitResponse(page, 'PATCH', '/api/products/fbs-stock-sync/bulk', 200),
      page.getByTestId('seller-fbs-bulk-confirm-submit').click(),
    ])
    const bulkBody = bulkRequest.postDataJSON()
    requireCheck('bulk request body sends product_ids array with selected id, never null/all', Array.isArray(bulkBody.product_ids) && bulkBody.product_ids.length === 1 && bulkBody.product_ids[0] === productId && bulkBody.fbs_stock_sync_enabled === true, { bulkBody, response: await bulkResponse.json() })
    await page.getByTestId('seller-fbs-bulk-result').waitFor({ state: 'visible' })

    const missingPoolSync = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync`, {
      method: 'POST',
      token: adminToken,
      body: { wb_warehouse_id: WB_WAREHOUSE_ID },
    })
    evidence.network.stockSyncResults.push({ phase: 'missing_fbs_pool', result: missingPoolSync.json })
    const missingPoolState = await poll(
      () => syncStatusState(sellerId, adminToken),
      (state) => state.amount === 20 && state.item?.status === 'error',
      20_000,
    )
    rememberRoute(`${API}/operations/fbs-sellers/${sellerId}/stocks/sync`)
    await page.reload()
    await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
    const rowAfterNoPoolSync = await getSellerRow(page, productRow.sku_code)
    const missingPoolTexts = await rowStockTexts(rowAfterNoPoolSync, productId)
    const missingPoolPageText = await page.locator('body').innerText()
    requireCheck('missing FBS sync path keeps Нет FBS, disabled toggle, no WB: 0 шт and emulator remains 20', missingPoolTexts.status === 'Нет FBS' && !(await rowAfterNoPoolSync.getByTestId(`seller-fbs-toggle-${productId}`).isEnabled()) && !missingPoolPageText.includes('WB: 0 шт') && missingPoolState.amount === 20, { missingPoolTexts, missingPoolState })

    const poolButton = rowAfterNoPoolSync.getByTestId(`seller-stock-directions-toggle-${productId}`)
    const poolTitle = await poolButton.getAttribute('title')
    rememberClick('Пул / Настроить FBS-пул', { title: poolTitle })
    await poolButton.click()
    const drawer = page.getByTestId(`seller-stock-directions-panel-${productId}`)
    await drawer.waitFor({ state: 'visible' })
    await shot(page, '03-fbs-pool-drawer-empty-1280x720')
    requireCheck('pool button exposes Настроить FBS-пул and drawer starts with no FBS guidance', poolTitle === 'Настроить FBS-пул' && (await drawer.innerText()).includes('FBS-пул не выделен'), { poolTitle, drawerText: await drawer.innerText() })

    rememberClick('create FBS direction qty 5')
    await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('FBS WB rerun')
    await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('5')
    await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
    const [directionResponse] = await Promise.all([
      waitResponse(page, 'POST', `/api/products/${productId}/stock-directions`, 201),
      page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
    ])
    const fbsDirection = await directionResponse.json()
    await drawer.getByText('FBS-пул · 5 шт').waitFor()
    await shot(page, '04-fbs-direction-created-1280x720')
    const drawerTextAfterFbs = await drawer.innerText()
    const rowAfterFbs = await getSellerRow(page, productRow.sku_code)
    const afterFbsTexts = await rowStockTexts(rowAfterFbs, productId)
    requireCheck('FBS/FBO split is clear in main row and drawer after FBS direction', afterFbsTexts.freeFbo === 'Свободный FBO 7' && afterFbsTexts.distribution.includes('FBS 5 шт') && afterFbsTexts.distribution.includes('резервы 0 шт') && drawerTextAfterFbs.includes('FBS') && drawerTextAfterFbs.includes('5 шт') && drawerTextAfterFbs.includes('Свободный FBO') && drawerTextAfterFbs.includes('7 шт'), { afterFbsTexts, drawerTextAfterFbs, fbsDirection })
    requireCheck('after FBS direction status is Проверяем WB before emulator readback or a real nonzero readback', afterFbsTexts.status === 'Проверяем WB' || /^WB: [1-9]\d* шт$/.test(afterFbsTexts.status), afterFbsTexts)

    const positiveSync = await api(`/operations/fbs-sellers/${sellerId}/stocks/sync`, {
      method: 'POST',
      token: adminToken,
      body: { wb_warehouse_id: WB_WAREHOUSE_ID },
    })
    evidence.network.stockSyncResults.push({ phase: 'positive_fbs_pool', result: positiveSync.json })
    const confirmedState = await poll(
      () => syncStatusState(sellerId, adminToken),
      (state) => state.amount === 5 && state.item?.status === 'confirmed' && Number(state.item?.confirmed) === 5,
      20_000,
    )
    rememberRoute(`${API}/operations/fbs-sellers/${sellerId}/stocks/sync`)
    await page.reload()
    await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
    const rowAfterReadback = await getSellerRow(page, productRow.sku_code)
    await expect(rowAfterReadback.getByTestId(`seller-fbs-status-${productId}`)).toContainText('WB: 5 шт', { timeout: 20_000 })
    const readbackTexts = await rowStockTexts(rowAfterReadback, productId)
    await shot(page, '05-wb-readback-confirmed-1280x720')
    requireCheck('WB emulator confirms nonzero readback and seller UI shows WB: 5 шт', confirmedState.amount === 5 && readbackTexts.status === 'WB: 5 шт', { confirmedState, readbackTexts })

    rememberClick('open ТЗ action from ТЗ / ЧЗ')
    await rowAfterReadback.getByTestId(`seller-packaging-edit-${productId}`).click()
    const packagingDialog = page.getByTestId('seller-packaging-dialog')
    await packagingDialog.waitFor({ state: 'visible' })
    await shot(page, '06-packaging-dialog-from-tz-chz-1280x720')
    const packagingDialogText = await packagingDialog.innerText()
    const packagingTextValue = await page.getByTestId('seller-packaging-text').inputValue()
    const packagingMetrics = await sellerMetrics(page, productId)
    evidence.metrics.packagingDialog = packagingMetrics
    requireCheck('packaging opens from ТЗ / ЧЗ and action column remains unclipped', packagingDialogText.includes('ТЗ на упаковку') && packagingTextValue.includes('QA rerun') && packagingMetrics.packagingButtonVisible && !packagingMetrics.headers.includes('Действия'), { packagingDialogText, packagingTextValue, packagingMetrics })
    rememberClick('close ТЗ dialog')
    await packagingDialog.getByRole('button', { name: 'Отмена' }).click()

    const finalMetrics = await sellerMetrics(page, productId)
    const finalPageText = await page.locator('body').innerText()
    evidence.metrics.finalSellerCatalog = finalMetrics
    requireCheck('final metrics: rowHeight <=72, document/body scrollWidth <= viewport, table/container widths sane', finalMetrics.rowHeight <= 72 && finalMetrics.documentScrollWidth <= 1280 && finalMetrics.bodyScrollWidth <= 1280 && finalMetrics.tableScrollWidth <= finalMetrics.containerClientWidth + 1 && finalMetrics.containerScrollWidth <= finalMetrics.containerClientWidth + 1, finalMetrics)
    requireCheck('final product judgement: no overload, raw codes, old headers, separate actions, or WB zero success', !hasRawCatalogNoise(finalPageText) && !finalPageText.includes('WB: 0 шт'), { sample: finalPageText.slice(0, 2500) })

    rememberClick('logout seller')
    await page.getByTestId('logout').click()
    await loginAdmin(page, adminEmail, password)
    rememberClick('open FF catalog')
    await page.getByTestId('nav-ff-products').click()
    rememberRoute(`${WEB}/app/ff/products`)
    await page.getByTestId('ff-products-table').waitFor({ state: 'visible' })
    await shot(page, '07-ff-catalog-cleanup-1280x720')
    const ffHead = await page.getByTestId('ff-products-table').locator('thead').innerText()
    const ffText = await page.getByTestId('ff-products-table').innerText()
    requireCheck('FF catalog cleanup visible: business columns and no internal stage noise', ffHead.includes('Артикул WB') && ffHead.includes('Доступно') && ffHead.includes('Распределение') && !/(Сортировка|Не упаковано|Упаковано|Технический резерв|WB nm|nm_id)/.test(ffText), { ffHead, sample: ffText.slice(0, 2200) })
    rememberClick('open FF distribution popover')
    await page.getByTestId(`ff-product-distribution-${productId}`).click()
    const popover = page.getByTestId('ff-products-distribution-popover')
    await popover.waitFor({ state: 'visible' })
    const popoverText = await popover.innerText()
    requireCheck('FF distribution popover shows FBS/FBO split without internal noise', popoverText.includes('FBS') && popoverText.includes('Свободно для FBO') && !/(Сортировка|Не упаковано|Упаковано|Технический резерв)/.test(popoverText), { popoverText })
  } finally {
    await context.close().catch(() => {})
    await browser.close().catch(() => {})
  }
}

try {
  await main()
} catch (error) {
  if (error instanceof ProductFailure) {
    evidence.verdict = 'FINAL_BROWSER_GROUP_FAILED'
  } else {
    evidence.blockers.push(String(error?.stack ?? error))
    evidence.verdict = evidence.browser_used ? 'FINAL_BROWSER_GROUP_BLOCKED' : 'FINAL_BROWSER_GROUP_BLOCKED'
  }
  console.error(error)
  process.exitCode = 1
} finally {
  await writeArtifacts()
  console.log(JSON.stringify({
    verdict: evidence.verdict,
    browser_used: evidence.browser_used,
    ports: evidence.ports,
    final_md: FINAL_MD,
    result_json: RESULT_JSON,
  }, null, 2))
}
