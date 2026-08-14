import { chromium, request } from '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/frontend/node_modules/@playwright/test/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'

const ROOT = '/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812'
const EVIDENCE = path.join(
  ROOT,
  'docs/reviews/product-operations-ux/2026-08-12/evidence/f08-browser-product-qa-final',
)
const WEB = process.env.F08_WEB_ORIGIN ?? 'http://127.0.0.1:15108'
const API = process.env.F08_API_ORIGIN ?? 'http://127.0.0.1:18108'
const suffix = String(Date.now())
const password = 'password123'
const adminEmail = `f08-browser-admin-${suffix}@example.com`
const sellerEmail = `f08-browser-seller-${suffix}@example.com`
const sku = `SKU-F08-${suffix}`

const results = []
const commands = [
  `DATABASE_URL='sqlite+aiosqlite:///${path.join(EVIDENCE, 'f08-browser-qa.sqlite')}' WMS_AUTO_CREATE_SCHEMA=1 JWT_SECRET_KEY='qa-jwt-secret-key-minimum-32-characters-long' E2E_MOCK_WB_CARDS=1 E2E_MOCK_WB_SUPPLIES=1 E2E_MOCK_WB_WAREHOUSES=1 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18108`,
  `VITE_API_PROXY='${API}' E2E_SELLER_PATH_PREFIX='/seller' VITE_SELLER_PORTAL_URL='${WEB}/seller/' npm run dev -- --host 127.0.0.1 --port 15108`,
  `F08_WEB_ORIGIN='${WEB}' F08_API_ORIGIN='${API}' node docs/reviews/product-operations-ux/2026-08-12/evidence/f08-browser-product-qa-final/f08-browser-product-qa-final.mjs`,
]

function mark(ok, name, detail = '') {
  results.push({ ok, name, detail })
  if (!ok) throw new Error(`${name}: ${detail}`)
}

async function screenshot(page, name) {
  const file = path.join(EVIDENCE, `${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  return file
}

async function post(api, url, token, data, expected = [200, 201]) {
  const res = await api.post(url, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data,
  })
  if (!expected.includes(res.status())) {
    throw new Error(`POST ${url} -> ${res.status()} ${await res.text()}`)
  }
  return res.json()
}

async function getJson(api, url, token) {
  const res = await api.get(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok()) throw new Error(`GET ${url} -> ${res.status()} ${await res.text()}`)
  return res.json()
}

async function waitForMethod(page, method, part, status) {
  return page.waitForResponse((r) => {
    return r.request().method() === method && r.url().includes(part) && r.status() === status
  })
}

async function loginSeller(page) {
  await page.goto(`${WEB}/seller/`)
  await page.getByTestId('login-form').waitFor({ state: 'visible' })
  await page.getByTestId('login-form').getByLabel('Email').fill(sellerEmail)
  await page.getByTestId('login-form').getByLabel('Пароль').fill('')
  await Promise.all([
    waitForMethod(page, 'POST', '/api/auth/login', 403),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]).catch(async () => {
    await page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click()
  })
  if (await page.getByTestId('seller-password-setup-form').isVisible().catch(() => false)) {
    await page.getByTestId('seller-password-setup-form').getByLabel('Новый пароль').fill(password)
    await page.getByTestId('seller-password-setup-form').getByLabel('Повтор пароля').fill(password)
    await Promise.all([
      waitForMethod(page, 'POST', '/api/auth/set-initial-password', 200),
      page.getByTestId('seller-password-setup-submit').click(),
    ])
  } else {
    await page.getByTestId('login-form').getByLabel('Пароль').fill(password)
    await Promise.all([
      waitForMethod(page, 'POST', '/api/auth/login', 200),
      page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
    ])
  }
  await page.getByTestId('app-frame').waitFor({ state: 'visible' })
}

async function loginFf(page) {
  await page.goto(`${WEB}/`)
  const form = page.getByTestId('login-form')
  if (await form.isVisible().catch(() => false)) {
    await form.getByLabel('Email').fill(adminEmail)
    await form.getByLabel('Пароль').fill(password)
    await Promise.all([
      waitForMethod(page, 'POST', '/api/auth/login', 200),
      form.getByRole('button', { name: 'Войти' }).click(),
    ])
  }
  await page.getByTestId('app-frame').waitFor({ state: 'visible' })
}

async function collectSellerGeometry(page, productId) {
  return page.getByTestId('seller-product-row').filter({ hasText: sku }).evaluate((row, productId) => {
    const fbsCell = row.querySelector(`[data-testid="seller-fbs-cell-${productId}"]`)
    const table = row.closest('table')
    const container = row.closest('.MuiTableContainer-root')
    return {
      viewportWidth: window.innerWidth,
      bodyScrollWidth: document.body.scrollWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      tableScrollWidth: table?.scrollWidth ?? 0,
      tableContainerClientWidth: container?.clientWidth ?? 0,
      tableContainerScrollWidth: container?.scrollWidth ?? 0,
      rowHeight: row.getBoundingClientRect().height,
      rowText: row.textContent ?? '',
      fbsCellText: fbsCell?.textContent ?? '',
      limitControls: row.querySelectorAll('[data-testid^="seller-fbs-limit-"]').length,
    }
  }, productId)
}

async function main() {
  await fs.mkdir(EVIDENCE, { recursive: true })
  const api = await request.newContext({ baseURL: API })
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ baseURL: WEB, viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  page.setDefaultTimeout(20_000)

  const browserVersion = await browser.version()
  const health = await api.get('/health')
  mark(health.ok(), 'API health-check', `${health.status()}`)

  await page.goto('/')
  await page.getByTestId('go-to-register').click()
  await page.getByTestId('register-form').getByLabel('Организация').fill('F08 Browser QA FF')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  const reg = await Promise.all([
    waitForMethod(page, 'POST', '/api/auth/register', 200),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = (await reg[0].json()).access_token
  mark(Boolean(token), 'FF registration and token', adminEmail)

  const seller = await post(api, '/sellers', token, { name: 'F08 Direction Brand' })
  const sellerId = seller.id
  await post(api, '/auth/seller-accounts', token, { seller_id: sellerId, email: sellerEmail }, [200, 201])
  const warehouse = await post(api, '/warehouses', token, { name: 'F08 WH', code: `F08-WH-${suffix}` })
  const location = await post(api, `/warehouses/${warehouse.id}/locations`, token, { code: 'F08-LOC' })
  const product = await post(api, '/products', token, {
    name: 'F08 compact product with long human name that must not stretch the catalog row',
    sku_code: sku,
    length_mm: 10,
    width_mm: 10,
    height_mm: 10,
    seller_id: sellerId,
  })
  const productId = product.id

  const inbound = await post(api, '/operations/inbound-intake-requests', token, { warehouse_id: warehouse.id })
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/lines`, token, {
    product_id: productId,
    expected_qty: 10,
    storage_location_id: location.id,
  })
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/submit`, token, {}, [200])
  const detailBefore = await getJson(api, `/operations/inbound-intake-requests/${inbound.id}`, token)
  const lineId = detailBefore.lines[0].id
  const patchActual = await api.patch(`/operations/inbound-intake-requests/${inbound.id}/lines/${lineId}/actual`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: { actual_qty: 0 },
  })
  mark(patchActual.ok(), 'Inbound receiving started', `${patchActual.status()}`)
  const box = await post(api, `/operations/inbound-intake-requests/${inbound.id}/boxes`, token, {}, [201])
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/boxes/open`, token, { barcode: box.internal_barcode }, [200])
  for (let i = 0; i < 10; i += 1) {
    await post(api, `/operations/inbound-intake-requests/${inbound.id}/boxes/${box.id}/scan`, token, { barcode: sku }, [200])
  }
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/boxes/${box.id}/close`, token, {}, [200])
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/verify`, token, {}, [200])
  await post(api, `/operations/inbound-intake-requests/${inbound.id}/post`, token, {}, [200])
  mark(true, 'Physical stock seeded via inbound operations', `${sku}: 10`)

  await page.getByTestId('logout').click()
  await loginSeller(page)
  await page.getByTestId('nav-seller-products').click()
  await page.getByTestId('seller-products-table').waitFor({ state: 'visible' })
  await page.getByTestId('seller-products-search').fill(sku).catch(() => {})
  const row = page.getByTestId('seller-product-row').filter({ hasText: sku })
  await row.waitFor({ state: 'visible' })
  await screenshot(page, '01-seller-catalog-initial-1280')

  const pageTextInitial = await page.locator('body').innerText()
  mark(!pageTextInitial.includes('Включить всем'), 'No bulk enable button', 'bulk enable text absent')
  mark(!pageTextInitial.includes('Выключить всем'), 'No bulk disable button', 'bulk disable text absent')
  mark(!(await row.innerText()).includes('Лимит'), 'No per-row Limit field', 'Лимит absent in product row')
  mark((await row.getByTestId(`seller-fbs-status-${productId}`).innerText()).includes('FBS-пул не выделен'), 'No FBS pool status is human', 'FBS-пул не выделен')
  mark(!(await row.getByTestId(`seller-fbs-toggle-${productId}`).isEnabled()), 'No FBS pool toggle disabled', 'toggle disabled before FBS direction')

  await row.getByTestId(`seller-stock-directions-toggle-${productId}`).click()
  const panel = page.getByTestId(`seller-stock-directions-panel-${productId}`)
  await panel.waitFor({ state: 'visible' })
  await screenshot(page, '02-seller-directions-panel-empty-fbs')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('FBS WB')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('3')
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
  const fbsCreate = await Promise.all([
    waitForMethod(page, 'POST', `/api/products/${productId}/stock-directions`, 201),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  const fbsDirectionId = (await fbsCreate[0].json()).id
  await row.getByText('FBS 3 шт').waitFor()
  mark((await row.getByTestId(`seller-fbs-toggle-${productId}`).isEnabled()), 'FBS direction enables safe publication toggle', 'toggle enabled after FBS allocation')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Набор сентябрь')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('2')
  const reserveCreate = await Promise.all([
    waitForMethod(page, 'POST', `/api/products/${productId}/stock-directions`, 201),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  const reserveDirectionId = (await reserveCreate[0].json()).id
  await row.getByText('резервы 2 шт').waitFor()

  await page.getByTestId(`seller-stock-direction-edit-${reserveDirectionId}`).click()
  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Набор сентябрь long comment')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('4')
  await page.getByTestId(`seller-stock-direction-comment-${productId}`).fill('Длинный комментарий не должен раздувать таблицу товаров')
  await Promise.all([
    waitForMethod(page, 'PATCH', `/api/products/stock-directions/${reserveDirectionId}`, 200),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await panel.getByText('Резерв/набор · 4 шт').waitFor()

  await page.getByTestId(`seller-stock-direction-edit-${reserveDirectionId}`).click()
  await page.getByTestId(`seller-stock-direction-fbs-${productId}`).click()
  await Promise.all([
    waitForMethod(page, 'PATCH', `/api/products/stock-directions/${reserveDirectionId}`, 200),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  await row.getByText('FBS 7 шт').waitFor()
  await screenshot(page, '03-seller-after-create-edit-directions')

  await page.getByTestId(`seller-stock-direction-name-${productId}`).fill('Слишком много')
  await page.getByTestId(`seller-stock-direction-quantity-${productId}`).fill('4')
  await Promise.all([
    waitForMethod(page, 'POST', `/api/products/${productId}/stock-directions`, 422),
    page.getByTestId(`seller-stock-direction-submit-${productId}`).click(),
  ])
  const errorText = await page.getByTestId('seller-products-error').innerText()
  mark(errorText.includes('Нельзя распределить больше, чем есть на ФФ'), 'Excess stock error is human', errorText)
  mark(!errorText.includes('directions_exceed_stock'), 'Raw stock-direction error hidden', errorText)
  await screenshot(page, '04-seller-human-error-excess-stock')

  let deleteRequests = 0
  page.on('request', (request) => {
    if (request.method() === 'DELETE' && request.url().includes(`/api/products/stock-directions/${fbsDirectionId}`)) {
      deleteRequests += 1
    }
  })
  await page.getByTestId(`seller-stock-direction-delete-${fbsDirectionId}`).click()
  const dialog = page.getByTestId('seller-stock-direction-delete-dialog')
  await dialog.waitFor({ state: 'visible' })
  await screenshot(page, '05-seller-delete-confirmation')
  await dialog.getByRole('button', { name: 'Отмена' }).click()
  mark(deleteRequests === 0, 'Delete cancel does not call DELETE', `DELETE requests: ${deleteRequests}`)
  await page.getByTestId(`seller-stock-direction-delete-${fbsDirectionId}`).click()
  await Promise.all([
    waitForMethod(page, 'DELETE', `/api/products/stock-directions/${fbsDirectionId}`, 204),
    page.getByTestId('seller-stock-direction-confirm-delete').click(),
  ])
  mark(deleteRequests === 1, 'Delete requires confirmation', `DELETE requests: ${deleteRequests}`)

  const sellerGeometry = await collectSellerGeometry(page, productId)
  mark(sellerGeometry.rowHeight <= 96, 'Seller product row compact at 1280px', `rowHeight=${sellerGeometry.rowHeight}`)
  mark(sellerGeometry.documentScrollWidth <= sellerGeometry.viewportWidth + 1, 'No document horizontal overflow / black strip', JSON.stringify(sellerGeometry))
  mark(sellerGeometry.bodyScrollWidth <= sellerGeometry.viewportWidth + 1, 'No body horizontal overflow', JSON.stringify(sellerGeometry))
  mark(sellerGeometry.tableScrollWidth <= sellerGeometry.tableContainerClientWidth + 1, 'Seller table does not overflow container', JSON.stringify(sellerGeometry))
  mark(!sellerGeometry.rowText.includes('Лимит'), 'Limit remains absent after CRUD', sellerGeometry.fbsCellText)
  mark(sellerGeometry.limitControls === 0, 'No hidden seller-fbs-limit controls', `count=${sellerGeometry.limitControls}`)
  mark(!/directions_exceed_stock|pending|confirmed|conflict|undefined|null|NaN/.test(await page.locator('body').innerText()), 'No technical/raw texts on seller screen', 'raw technical strings absent')

  await page.getByTestId('logout').click()
  await loginFf(page)
  await page.getByTestId('nav-ff-products').click()
  await page.getByTestId('ff-products-table').waitFor({ state: 'visible' })
  await page.getByTestId('ff-products-search').fill(sku)
  await page.getByTestId(`ff-product-distribution-${productId}`).click()
  await page.getByTestId('ff-products-distribution-popover').waitFor({ state: 'visible' })
  await page.waitForTimeout(300)
  await screenshot(page, '06-ff-catalog-distribution-popover')
  await page.getByTestId('ff-products-distribution-popover').screenshot({
    path: path.join(EVIDENCE, '07-ff-catalog-distribution-popover-element.png'),
  })
  const popoverGeometry = await page.evaluate(() => {
    const pop = document.querySelector('[data-testid="ff-products-distribution-popover"]')
    const paper = pop?.closest('.MuiPopover-paper')
    return {
      viewportWidth: window.innerWidth,
      bodyScrollWidth: document.body.scrollWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      popoverWidth: paper?.getBoundingClientRect().width ?? 0,
      popoverRight: paper?.getBoundingClientRect().right ?? 0,
      popoverText: pop?.textContent ?? '',
    }
  })
  mark(popoverGeometry.documentScrollWidth <= popoverGeometry.viewportWidth + 1, 'FF popover does not widen document', JSON.stringify(popoverGeometry))
  mark(popoverGeometry.bodyScrollWidth <= popoverGeometry.viewportWidth + 1, 'FF popover does not widen body', JSON.stringify(popoverGeometry))
  mark(popoverGeometry.popoverRight <= popoverGeometry.viewportWidth + 1, 'FF popover stays in viewport', JSON.stringify(popoverGeometry))
  mark(popoverGeometry.popoverText.includes('FBS') && popoverGeometry.popoverText.includes('Свободно для FBO'), 'FF popover content is business-readable', popoverGeometry.popoverText)
  mark(!/Лимит|Включить всем|Выключить всем|directions_exceed_stock|pending|confirmed|conflict|undefined|null|NaN/.test(await page.locator('body').innerText()), 'No overloaded/technical text in FF catalog view', 'forbidden strings absent')

  const evidenceJson = {
    verdict: 'BROWSER_PRODUCT_QA_PASSED',
    date: new Date().toISOString(),
    gitRoot: ROOT,
    web: WEB,
    api: API,
    browser: browserVersion,
    seed: { adminEmail, sellerEmail, sku, productId, sellerId },
    sellerGeometry,
    popoverGeometry,
    checks: results,
    commands,
    screenshots: [
      '01-seller-catalog-initial-1280.png',
      '02-seller-directions-panel-empty-fbs.png',
      '03-seller-after-create-edit-directions.png',
      '04-seller-human-error-excess-stock.png',
      '05-seller-delete-confirmation.png',
      '06-ff-catalog-distribution-popover.png',
      '07-ff-catalog-distribution-popover-element.png',
    ],
  }
  await fs.writeFile(path.join(EVIDENCE, 'f08-browser-product-qa-final.json'), JSON.stringify(evidenceJson, null, 2))
  const md = `# F08 Browser Product QA Final

Дата: 2026-08-13, Europe/Moscow.
Git-root: \`${ROOT}\`.
Роль: independent Browser Product QA Agent.
Статус: \`BROWSER_PRODUCT_QA_PASSED\`.

## UX Verdict

F08 directions / FBS pool после geometry rework проходит живую браузерную продуктовую проверку на 1280px. Seller product catalog открывается, строка товара компактная, отдельного поля/колонки \`Лимит\` и bulk \`Включить всем\` / \`Выключить всем\` нет. До выделения FBS-пула статус понятный: \`FBS-пул не выделен\`, toggle выключен. Создание FBS-направления, создание резерва, изменение направления, перевод резерва в FBS и удаление через подтверждение проходят кликами в UI. Ошибка превышения остатка показана человеческим текстом, raw \`directions_exceed_stock\` не виден.

FF catalog distribution popover не раздвигает body/document и остается в viewport. Экран не выглядит перегруженным техническими чипами, raw-статусами или лишними bulk-действиями.

## Evidence

- Browser: ${browserVersion}
- Web: \`${WEB}\`
- API: \`${API}\`
- Seed: \`${sku}\`, product \`${productId}\`
- Seller geometry: \`${JSON.stringify(sellerGeometry)}\`
- FF popover geometry: \`${JSON.stringify(popoverGeometry)}\`
- Screenshots:
  - \`01-seller-catalog-initial-1280.png\`
  - \`02-seller-directions-panel-empty-fbs.png\`
  - \`03-seller-after-create-edit-directions.png\`
  - \`04-seller-human-error-excess-stock.png\`
  - \`05-seller-delete-confirmation.png\`
  - \`06-ff-catalog-distribution-popover.png\`
  - \`07-ff-catalog-distribution-popover-element.png\`

## Commands

\`\`\`bash
${commands.join('\n')}
\`\`\`

## Checks

${results.map((r) => `- ${r.ok ? 'PASS' : 'FAIL'}: ${r.name}${r.detail ? ` — ${r.detail}` : ''}`).join('\n')}
`
  await fs.writeFile(path.join(EVIDENCE, 'F08_BROWSER_PRODUCT_QA_FINAL_RU.md'), md)
  await context.close()
  await browser.close()
  await api.dispose()
}

main().catch(async (error) => {
  const md = `# F08 Browser Product QA Final

Дата: 2026-08-13, Europe/Moscow.
Git-root: \`${ROOT}\`.
Роль: independent Browser Product QA Agent.
Статус: \`BROWSER_PRODUCT_QA_FAILED\`.

## Failure

\`${error?.stack ?? error}\`

## Completed Checks

${results.map((r) => `- ${r.ok ? 'PASS' : 'FAIL'}: ${r.name}${r.detail ? ` — ${r.detail}` : ''}`).join('\n')}

## Commands

\`\`\`bash
${commands.join('\n')}
\`\`\`
`
  await fs.writeFile(path.join(EVIDENCE, 'F08_BROWSER_PRODUCT_QA_FINAL_RU.md'), md)
  process.exit(1)
})
