#!/usr/bin/env node
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const evidenceDir = path.dirname(__filename)
const rootDir = path.resolve(evidenceDir, '../../../../../..')
const backendDir = path.join(rootDir, 'backend')
const frontendDir = path.join(rootDir, 'frontend')
const logsDir = path.join(evidenceDir, 'logs')
const screenshotsDir = path.join(evidenceDir, 'screenshots')
const dataDir = path.join(evidenceDir, 'data')
const dbPath = path.join(dataDir, 'f10-browser-product-qa.sqlite3')
const password = 'password123'
const marketplaceToken = 'qa-local-wb-token'
const forbiddenMainUiPattern =
  /Лимит|pending_confirmation|warehouse_mapping_missing|unsafe_stock_unknown|unsafe_zero_blocked|ambiguous_warehouse_scope|wb_upstream_error|readback_mismatch|duplicate_chrt_id|conflict/

const { chromium } = await import(
  pathToFileURL(path.join(frontendDir, 'node_modules/playwright/index.mjs')).href
)

function nowSuffix() {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

async function getFreePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : null
      server.close(() => {
        if (port == null) reject(new Error('no free port'))
        else resolve(port)
      })
    })
  })
}

function startLoggedProcess(name, command, args, options) {
  const log = createWriteStream(path.join(logsDir, `${name}.log`), { flags: 'a' })
  const child = spawn(command, args, {
    ...options,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  child.stdout.on('data', (chunk) => log.write(chunk))
  child.stderr.on('data', (chunk) => log.write(chunk))
  child.on('exit', (code, signal) => {
    log.write(`\n[exit code=${code} signal=${signal}]\n`)
    log.end()
  })
  return child
}

async function waitForHttp(url, { timeoutMs = 60_000 } = {}) {
  const started = Date.now()
  let lastError = null
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = new Error(`${url}: ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw lastError ?? new Error(`timed out waiting for ${url}`)
}

function startWbMock() {
  const stocks = new Map()
  const putCalls = []
  const postCalls = []
  const key = (warehouseId, chrtId) => `${warehouseId}:${chrtId}`
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1')
    const stocksMatch = url.pathname.match(/^\/api\/v3\/stocks\/(\d+)$/)
    if (!stocksMatch) {
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ detail: 'not_found' }))
      return
    }
    const warehouseId = Number(stocksMatch[1])
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const rawBody = Buffer.concat(chunks).toString('utf8') || '{}'
    const body = JSON.parse(rawBody)
    if (req.method === 'PUT') {
      const batch = Array.isArray(body.stocks) ? body.stocks : []
      putCalls.push({ warehouseId, stocks: batch.map((row) => ({ ...row })) })
      for (const row of batch) {
        stocks.set(key(warehouseId, Number(row.chrtId)), Number(row.amount))
      }
      res.writeHead(204)
      res.end()
      return
    }
    if (req.method === 'POST') {
      const chrtIds = Array.isArray(body.chrtIds) ? body.chrtIds.map(Number) : []
      postCalls.push({ warehouseId, chrtIds })
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          stocks: chrtIds.map((chrtId) => ({
            chrtId,
            amount: Number(stocks.get(key(warehouseId, chrtId)) ?? 0),
          })),
        }),
      )
      return
    }
    res.writeHead(405, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'method_not_allowed' }))
  })
  return { server, stocks, putCalls, postCalls }
}

async function listen(server, port) {
  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve))
}

async function apiJson(apiBase, pathName, { method = 'GET', token, body } = {}) {
  const response = await fetch(`${apiBase}${pathName}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let parsed = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }
  if (!response.ok) {
    throw new Error(`${method} ${pathName}: ${response.status} ${text}`)
  }
  return parsed
}

async function runPythonSeed(payload, env) {
  const seedPath = path.join(evidenceDir, 'f10_seed_db.py')
  const child = spawn(
    'python3',
    [seedPath, '--payload', JSON.stringify(payload)],
    {
      cwd: backendDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  let stdout = ''
  let stderr = ''
  child.stdout.on('data', (chunk) => {
    stdout += chunk.toString()
  })
  child.stderr.on('data', (chunk) => {
    stderr += chunk.toString()
  })
  const exitCode = await new Promise((resolve) => child.on('exit', resolve))
  if (exitCode !== 0) {
    throw new Error(`seed failed (${exitCode}): ${stderr}`)
  }
  return JSON.parse(stdout)
}

async function createScenario(apiBase, token, suffix, kind) {
  const sellerName = kind === 'positive' ? `F10 Positive Seller ${suffix}` : `F10 Ambiguous Seller ${suffix}`
  const sellerEmail =
    kind === 'positive'
      ? `f10-positive-seller-${suffix}@example.com`
      : `f10-ambiguous-seller-${suffix}@example.com`
  const seller = await apiJson(apiBase, '/sellers/with-account', {
    method: 'POST',
    token,
    body: { name: sellerName, email: sellerEmail, password },
  })
  const warehouse = await apiJson(apiBase, '/warehouses', {
    method: 'POST',
    token,
    body: {
      name: kind === 'positive' ? 'F10 FBS WH Positive' : 'F10 FBS WH Ambiguous A',
      code: kind === 'positive' ? `f10-pos-${suffix}` : `f10-amb-a-${suffix}`,
    },
  })
  const location = await apiJson(apiBase, `/warehouses/${warehouse.id}/locations`, {
    method: 'POST',
    token,
    body: { code: kind === 'positive' ? 'F10-POS-LOC' : 'F10-AMB-LOC' },
  })
  let secondWarehouse = null
  if (kind === 'ambiguous') {
    secondWarehouse = await apiJson(apiBase, '/warehouses', {
      method: 'POST',
      token,
      body: {
        name: 'F10 FBS WH Ambiguous B',
        code: `f10-amb-b-${suffix}`,
      },
    })
  }
  const sku = kind === 'positive' ? `SKU-F10-POS-${suffix}` : `SKU-F10-AMB-${suffix}`
  const product = await apiJson(apiBase, '/products', {
    method: 'POST',
    token,
    body: {
      name: kind === 'positive' ? 'F10 Positive Product' : 'F10 Ambiguous Product',
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: seller.seller_id,
      wb_barcode: kind === 'positive' ? `F10-POS-BAR-${suffix}` : `F10-AMB-BAR-${suffix}`,
    },
  })
  return { seller, sellerEmail, sellerName, warehouse, location, secondWarehouse, product, sku }
}

async function login(page, baseUrl, email, pass, portal) {
  await page.goto(portal === 'seller' ? `${baseUrl}/seller/` : `${baseUrl}/`)
  await page.getByTestId('login-form').waitFor({ state: 'visible' })
  await page.getByTestId('login-form').getByLabel('Email').fill(email)
  await page.getByTestId('login-form').getByLabel('Пароль').fill(pass)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/auth/login')),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ])
  await page.getByTestId('app-frame').waitFor({ state: 'visible' })
}

async function sellerProductRow(page, sku) {
  const nav = page.getByTestId('nav-seller-products')
  if (!(await nav.isVisible().catch(() => false))) {
    await page.goto('/seller/')
    await page.getByTestId('app-frame').waitFor({ state: 'visible' })
  }
  await page.getByTestId('nav-seller-products').click()
  await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await row.waitFor({ state: 'visible' })
  return row
}

async function withFreshPage(browser, baseURL, fn) {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1280, height: 720 },
  })
  const page = await context.newPage()
  try {
    return await fn(page)
  } catch (error) {
    await page.screenshot({
      path: path.join(screenshotsDir, `failure-${Date.now()}.png`),
      fullPage: true,
    }).catch(() => {})
    throw error
  } finally {
    await context.close()
  }
}

async function collectMainUiGeometry(page, row, productId) {
  return await row.evaluate((rowElement, targetProductId) => {
    const doc = document.documentElement
    const body = document.body
    const table = rowElement.closest('table')
    const container = rowElement.closest('.MuiTableContainer-root')
    const fbsCell = rowElement.querySelector(`[data-testid="seller-fbs-cell-${targetProductId}"]`)
    const tableText = table?.textContent ?? ''
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: doc.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      tableScrollWidth: table?.scrollWidth ?? 0,
      tableContainerClientWidth: container?.clientWidth ?? 0,
      tableContainerScrollWidth: container?.scrollWidth ?? 0,
      rowHeight: rowElement.getBoundingClientRect().height,
      fbsCellText: fbsCell?.textContent ?? '',
      tableText,
      fbsLimitControls: rowElement.querySelectorAll('[data-testid^="seller-fbs-limit-"]').length,
      blackStripElements: Array.from(document.querySelectorAll('*')).filter((el) => {
        const style = window.getComputedStyle(el)
        const rect = el.getBoundingClientRect()
        return (
          rect.width > window.innerWidth * 0.7 &&
          rect.height > 12 &&
          (style.backgroundColor === 'rgb(0, 0, 0)' || style.backgroundColor === '#000000')
        )
      }).length,
    }
  }, productId)
}

function assertCleanGeometry(geometry) {
  assert.equal(geometry.fbsLimitControls, 0)
  assert.equal(geometry.blackStripElements, 0)
  assert.ok(geometry.rowHeight <= 96, `row too tall: ${geometry.rowHeight}`)
  assert.ok(
    geometry.documentScrollWidth <= geometry.viewportWidth + 1,
    `document overflow ${geometry.documentScrollWidth} > ${geometry.viewportWidth}`,
  )
  assert.ok(
    geometry.bodyScrollWidth <= geometry.viewportWidth + 1,
    `body overflow ${geometry.bodyScrollWidth} > ${geometry.viewportWidth}`,
  )
  assert.ok(
    geometry.tableScrollWidth <= geometry.tableContainerClientWidth + 1,
    `table overflow ${geometry.tableScrollWidth} > ${geometry.tableContainerClientWidth}`,
  )
  assert.ok(
    geometry.tableContainerScrollWidth <= geometry.tableContainerClientWidth + 1,
    `container overflow ${geometry.tableContainerScrollWidth} > ${geometry.tableContainerClientWidth}`,
  )
  assert.ok(!forbiddenMainUiPattern.test(geometry.tableText), `forbidden main UI text: ${geometry.tableText}`)
}

async function runFfManualSync(page, baseUrl, adminEmail, scenario) {
  await page.goto(`${baseUrl}/app/ff/fbs/stock-sync`)
  if (await page.getByTestId('login-form').isVisible().catch(() => false)) {
    await login(page, baseUrl, adminEmail, password, 'ff')
    await page.goto(`${baseUrl}/app/ff/fbs/stock-sync`)
  }
  await page.getByTestId('fbs-stock-sync-screen').waitFor({ state: 'visible' })
  await page.getByTestId('fbs-stock-seller-filter').click()
  await page.getByRole('option', { name: scenario.sellerName }).click()
  await page.getByTestId('fbs-stock-binding-row').first().waitFor({ state: 'visible' })
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        res.url().includes(`/api/operations/fbs-sellers/${scenario.seller.seller_id}/stocks/sync`) &&
        res.status() === 200,
    ),
    page.getByTestId('fbs-stock-sync-all').click(),
  ])
  const body = await response.json()
  await page.getByTestId('fbs-stock-sync-feedback').waitFor({ state: 'visible' })
  return body
}

async function main() {
  await mkdir(logsDir, { recursive: true })
  await mkdir(screenshotsDir, { recursive: true })
  await mkdir(dataDir, { recursive: true })
  await rm(dbPath, { force: true })

  const suffix = nowSuffix()
  const apiPort = await getFreePort()
  const webPort = await getFreePort()
  const wbPort = await getFreePort()
  const apiBase = `http://127.0.0.1:${apiPort}`
  const webBase = `http://127.0.0.1:${webPort}`
  const wbBase = `http://127.0.0.1:${wbPort}`
  const databaseUrl = `sqlite+aiosqlite:///${dbPath}`
  const env = {
    ...process.env,
    WMS_AUTO_CREATE_SCHEMA: '1',
    PYTHONPATH: backendDir,
    DATABASE_URL: databaseUrl,
    JWT_SECRET_KEY: 'f10-browser-product-qa-local-secret-32',
    E2E_MOCK_WB_CARDS: '1',
    E2E_MOCK_WB_SUPPLIES: '1',
    E2E_MOCK_WB_WAREHOUSES: '1',
    E2E_MOCK_WB_MARKETPLACE_WAREHOUSES: '1',
    WILDBERRIES_MARKETPLACE_API_BASE: wbBase,
    WMS_DATA_DIR: dataDir,
  }

  const wbMock = startWbMock()
  await listen(wbMock.server, wbPort)
  const backend = startLoggedProcess('backend', 'python3', [
    '-m',
    'uvicorn',
    'app.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    String(apiPort),
  ], { cwd: backendDir, env })
  const frontend = startLoggedProcess('frontend', 'npm', [
    'run',
    'dev',
    '--',
    '--host',
    '127.0.0.1',
    '--port',
    String(webPort),
  ], {
    cwd: frontendDir,
    env: {
      ...process.env,
      VITE_API_PROXY: apiBase,
      E2E_SELLER_PATH_PREFIX: '/seller',
      VITE_SELLER_PORTAL_URL: `${webBase}/seller/`,
    },
  })

  const cleanup = async () => {
    for (const child of [frontend, backend]) {
      if (!child.killed) child.kill('SIGTERM')
    }
    await new Promise((resolve) => wbMock.server.close(resolve))
  }

  const evidence = {
    verdict: null,
    ports: { apiPort, webPort, wbPort },
    dbPath,
    startedAt: new Date().toISOString(),
    positive: {},
    ambiguous: {},
    visual: {},
    errors: [],
  }

  let browser
  try {
    await waitForHttp(`${apiBase}/health`, { timeoutMs: 60_000 })
    await waitForHttp(webBase, { timeoutMs: 60_000 })

    const adminEmail = `f10-final-admin-${suffix}@example.com`
    const admin = await apiJson(apiBase, '/auth/register', {
      method: 'POST',
      body: {
        organization_name: 'F10 Browser Product QA',
        slug: `f10-final-${suffix}`.replace(/[^a-z0-9-]/g, '-').slice(0, 60),
        admin_email: adminEmail,
        password,
      },
    })
    const adminToken = admin.access_token
    const positive = await createScenario(apiBase, adminToken, suffix, 'positive')
    const ambiguous = await createScenario(apiBase, adminToken, suffix, 'ambiguous')

    const positiveSeed = await runPythonSeed(
      {
        seller_id: positive.seller.seller_id,
        product_id: positive.product.id,
        warehouse_id: positive.warehouse.id,
        location_id: positive.location.id,
        chrt_id: 1210,
        wb_warehouse_id: 501001,
        nm_id: 901210,
        barcode: `F10-POS-BAR-${suffix}`,
        vendor_code: `F10-POS-${suffix}`,
        marketplace_token: marketplaceToken,
        physical_stock: 1000,
        fbs_pool: 200,
        reserve_pool: 300,
        active_fbs_reservation: 7,
        wb_order_id: 812010,
        fbs_direction_name: 'FBS pool for WB',
        reserve_direction_name: 'Sets and FBO reserve',
      },
      env,
    )
    const ambiguousSeed = await runPythonSeed(
      {
        seller_id: ambiguous.seller.seller_id,
        product_id: ambiguous.product.id,
        warehouse_id: ambiguous.warehouse.id,
        location_id: ambiguous.location.id,
        second_warehouse_id: ambiguous.secondWarehouse.id,
        chrt_id: 1211,
        wb_warehouse_id: 501101,
        second_wb_warehouse_id: 501102,
        nm_id: 901211,
        barcode: `F10-AMB-BAR-${suffix}`,
        vendor_code: `F10-AMB-${suffix}`,
        marketplace_token: marketplaceToken,
        physical_stock: 1000,
        fbs_pool: 200,
        reserve_pool: 300,
        active_fbs_reservation: 0,
        wb_order_id: 812011,
        fbs_direction_name: 'Ambiguous FBS pool',
        reserve_direction_name: 'Ambiguous non-FBS reserve',
      },
      env,
    )

    browser = await chromium.launch({ headless: true })
    const positiveBeforeGeometry = await withFreshPage(browser, webBase, async (page) => {
      await login(page, webBase, positive.sellerEmail, password, 'seller')
      const row = await sellerProductRow(page, positive.sku)
      await assertRowState(page, row, positive.product.id, {
        expectedDistribution: ['FBS 200 шт', 'резервы 300 шт'],
        expectedStock: { inStorage: '1000', freeFbo: '500' },
        expectedStatus: 'Проверяем WB',
      })
      const geometry = await collectMainUiGeometry(page, row, positive.product.id)
      assertCleanGeometry(geometry)
      await page.screenshot({
        path: path.join(screenshotsDir, 'positive-seller-before-sync.png'),
        fullPage: true,
      })
      return geometry
    })

    const positiveSync = await withFreshPage(browser, webBase, async (page) => {
      const result = await runFfManualSync(page, webBase, adminEmail, positive)
      await page.screenshot({
        path: path.join(screenshotsDir, 'positive-ff-manual-sync.png'),
        fullPage: true,
      })
      return result
    })
    assert.equal(positiveSync.products_targeted, 1)
    assert.equal(positiveSync.products_confirmed, 1)
    assert.equal(positiveSync.errors, 0)
    assert.deepEqual(
      wbMock.putCalls
        .filter((call) => call.warehouseId === 501001)
        .flatMap((call) => call.stocks.map((stock) => [Number(stock.chrtId), Number(stock.amount)])),
      [[1210, 193]],
    )
    assert.deepEqual(
      wbMock.postCalls
        .filter((call) => call.warehouseId === 501001)
        .map((call) => call.chrtIds),
      [[1210]],
    )
    assert.equal(wbMock.stocks.get('501001:1210'), 193)
    assert.notEqual(wbMock.stocks.get('501001:1210'), 1000)
    assert.notEqual(wbMock.stocks.get('501001:1210'), 500)

    const positiveAfterGeometry = await withFreshPage(browser, webBase, async (page) => {
      await login(page, webBase, positive.sellerEmail, password, 'seller')
      const row = await sellerProductRow(page, positive.sku)
      await assertRowState(page, row, positive.product.id, {
        expectedDistribution: ['FBS 200 шт', 'резервы 300 шт'],
        expectedStock: { inStorage: '1000', freeFbo: '500' },
        expectedStatus: 'WB: 193 шт',
      })
      const geometry = await collectMainUiGeometry(page, row, positive.product.id)
      assertCleanGeometry(geometry)
      await page.screenshot({
        path: path.join(screenshotsDir, 'positive-seller-after-readback.png'),
        fullPage: true,
      })
      return geometry
    })

    wbMock.stocks.set('501101:1211', 20)
    wbMock.stocks.set('501102:1211', 20)
    const putCountBeforeAmbiguous = wbMock.putCalls.length
    const postCountBeforeAmbiguous = wbMock.postCalls.length
    const ambiguousSync = await withFreshPage(browser, webBase, async (page) => {
      const result = await runFfManualSync(page, webBase, adminEmail, ambiguous)
      await page.screenshot({
        path: path.join(screenshotsDir, 'ambiguous-ff-fail-closed-sync.png'),
        fullPage: true,
      })
      return result
    })
    assert.equal(ambiguousSync.products_targeted, 0)
    assert.equal(ambiguousSync.products_confirmed, 0)
    assert.equal(ambiguousSync.errors, 2)
    assert.equal(wbMock.putCalls.length, putCountBeforeAmbiguous)
    assert.equal(wbMock.postCalls.length, postCountBeforeAmbiguous)
    assert.equal(wbMock.stocks.get('501101:1211'), 20)
    assert.equal(wbMock.stocks.get('501102:1211'), 20)
    const ambiguousGeometry = await withFreshPage(browser, webBase, async (page) => {
      await login(page, webBase, ambiguous.sellerEmail, password, 'seller')
      const ambiguousRow = await sellerProductRow(page, ambiguous.sku)
      await assertRowState(page, ambiguousRow, ambiguous.product.id, {
        expectedDistribution: ['FBS 200 шт', 'резервы 300 шт'],
        expectedStock: { inStorage: '1000', freeFbo: '500' },
        expectedStatus: 'Ошибка WB',
      })
      const geometry = await collectMainUiGeometry(page, ambiguousRow, ambiguous.product.id)
      assertCleanGeometry(geometry)
      assert.ok(!geometry.fbsCellText.includes('ambiguous_warehouse_scope'))
      await page.screenshot({
        path: path.join(screenshotsDir, 'ambiguous-seller-safe-error.png'),
        fullPage: true,
      })
      return geometry
    })

    evidence.verdict = 'BROWSER_PRODUCT_QA_PASSED'
    evidence.positive = {
      seed: positiveSeed,
      syncResult: positiveSync,
      wbPutCalls: wbMock.putCalls.filter((call) => call.warehouseId === 501001),
      wbPostCalls: wbMock.postCalls.filter((call) => call.warehouseId === 501001),
      wbReadbackAmount: wbMock.stocks.get('501001:1210'),
      sellerBeforeGeometry: positiveBeforeGeometry,
      sellerAfterGeometry: positiveAfterGeometry,
      sku: positive.sku,
    }
    evidence.ambiguous = {
      seed: ambiguousSeed,
      syncResult: ambiguousSync,
      wbPutCallsAdded: wbMock.putCalls.length - putCountBeforeAmbiguous,
      wbPostCallsAdded: wbMock.postCalls.length - postCountBeforeAmbiguous,
      wbReadbackAmounts: {
        '501101:1211': wbMock.stocks.get('501101:1211'),
        '501102:1211': wbMock.stocks.get('501102:1211'),
      },
      sellerGeometry: ambiguousGeometry,
      sku: ambiguous.sku,
    }
    evidence.visual = {
      viewport: { width: 1280, height: 720 },
      forbiddenMainUiPattern: String(forbiddenMainUiPattern),
      screenshots: [
        'screenshots/positive-seller-before-sync.png',
        'screenshots/positive-ff-manual-sync.png',
        'screenshots/positive-seller-after-readback.png',
        'screenshots/ambiguous-ff-fail-closed-sync.png',
        'screenshots/ambiguous-seller-safe-error.png',
      ],
    }
  } catch (error) {
    evidence.verdict = 'BROWSER_PRODUCT_QA_FAILED'
    evidence.errors.push(error instanceof Error ? error.stack ?? error.message : String(error))
    throw error
  } finally {
    if (browser) await browser.close()
    evidence.finishedAt = new Date().toISOString()
    await writeFile(
      path.join(evidenceDir, 'f10_browser_product_qa_result.json'),
      JSON.stringify(evidence, null, 2),
    )
    await cleanup()
  }
}

async function assertRowState(page, row, productId, expected) {
  const table = page.getByTestId('seller-products-table')
  const panel = page.getByTestId('seller-fbs-sync-panel')
  const tableText = await table.textContent()
  const panelText = await panel.textContent()
  assert.ok(!forbiddenMainUiPattern.test(tableText ?? ''), `forbidden table text: ${tableText}`)
  assert.ok(!(panelText ?? '').includes('Включить всем'))
  assert.ok(!(panelText ?? '').includes('Выключить всем'))
  for (const text of expected.expectedDistribution) {
    await row.getByTestId(`seller-stock-distribution-${productId}`).getByText(text).waitFor()
  }
  await row.getByTestId('seller-stock-in-storage').getByText(expected.expectedStock.inStorage).waitFor()
  await row.getByTestId('seller-stock-free-fbo').getByText(expected.expectedStock.freeFbo).waitFor()
  await row.getByTestId(`seller-fbs-status-${productId}`).getByText(expected.expectedStatus).waitFor()
  const fbsCellText = await row.getByTestId(`seller-fbs-cell-${productId}`).textContent()
  assert.ok(!(fbsCellText ?? '').includes('Лимит'))
  assert.ok(!(fbsCellText ?? '').includes('ambiguous_warehouse_scope'))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
