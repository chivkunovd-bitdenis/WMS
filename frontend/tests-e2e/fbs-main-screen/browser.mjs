// Actual SPA + WMS API + PostgreSQL. No page.route / WMS API interception.
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const { chromium, expect } = await import(process.env.WMS_PLAYWRIGHT_MODULE || '@playwright/test')
const root = process.env.FBS_MAIN_URL || 'http://127.0.0.1:15173'
assert(['127.0.0.1', 'localhost'].includes(new URL(root).hostname), 'Only disposable loopback stack is allowed')
const evidence = process.env.FBS_MAIN_EVIDENCE || 'artifacts/fbs-main-screen'
await mkdir(evidence, { recursive: true })
const seed = JSON.parse(await readFile(process.env.FBS_MAIN_SEED || `${evidence}/seed.json`, 'utf8'))
const fixture = seed.main
const browser = await chromium.launch({ headless: true })
const results = []
const selectedCases = process.env.FBS_MAIN_CASES?.split(',').filter(Boolean)
const wbDynamic = Object.values(seed.orders).flat().map(order => order.wms_order_id)
const orderId = key => fixture.orders[key].id
const sellerBIds = [orderId('wb_other_seller'), fixture.second_warehouse_order.id]
const newIds = [...wbDynamic, ...['wb_new', 'wb_other_seller', 'ozon_new', 'wb_unpublished'].map(orderId), fixture.second_warehouse_order.id]
let createdWbSupplyId = null

async function run(name, test, role = 'admin') {
  if (selectedCases && !selectedCases.includes(name)) return
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const page = await context.newPage()
  const errors = []
  const responses = []
  const worklistSnapshots = []
  let phase = 'setup'
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', async response => {
    if (response.url().includes('/api/operations/fbs')) responses.push({ url: response.url(), status: response.status() })
    if (response.url().includes('/fbs-orders/worklist') && response.ok()) {
      const body = await response.json().catch(() => null)
      if (body?.items) worklistSnapshots.push({ status: response.status(), ids: body.items.map(item => item.id) })
    }
  })
  try {
    const login = role === 'admin' ? seed.login : seed.role_logins[role]
    const response = await context.request.post(`${root}/api/auth/login`, { data: login })
    assert(response.ok(), `login failed: ${response.status()}`)
    const { access_token: token } = await response.json()
    await context.addInitScript(token => localStorage.setItem('wms_token_ff', token), token)
    await page.goto(`${root}/app/ff/fbs`)
    await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
    await expectIds(page, newIds)
    phase = 'test'
    await test(page, { context, token })
    assert.deepEqual(errors, [], 'Unhandled browser errors')
    results.push({ name, status: 'passed', responses })
  } catch (error) {
    const actualOrderIds = await page.getByTestId('fbs-worklist-table').locator('tbody tr[data-testid^="fbs-order-"]').evaluateAll(rows => rows.map(row => row.dataset.testid.slice('fbs-order-'.length))).catch(() => null)
    results.push({ name, status: 'failed', phase, error: String(error.stack || error), responses, worklistSnapshots, expectedOrderIds: [...newIds], actualOrderIds, browserErrors: errors })
  } finally {
    await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true }).catch(() => {})
    await context.close()
  }
}
async function expectIds(page, ids, type = 'order') {
  const prefix = type === 'order' ? 'fbs-order-' : 'fbs-18-supply-'
  const table = page.getByTestId(type === 'order' ? 'fbs-worklist-table' : 'fbs-18-supplies-table')
  await expect(table).toBeVisible()
  // DOM order follows deadline / last-update sorting; membership is the contract here.
  await expect.poll(async () => (await table.locator(`tbody tr[data-testid^="${prefix}"]`).evaluateAll(rows => rows.map(row => row.dataset.testid))).sort(), { timeout: 15000 }).toEqual(ids.map(id => prefix+id).sort())
}
async function choose(page, label, option) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}
async function search(page, value) {
  const input = page.getByTestId('fbs-worklist-search').locator('input')
  await input.fill(value)
  await input.press('Enter')
}
const row = (page, key) => page.getByTestId(`fbs-order-${orderId(key)}`)
const bar = page => page.getByTestId('fbs-selection-bar')

await run('S1-six-tabs-and-exact-membership', async page => {
  for (const tab of ['Новые', 'В работе', 'В доставке', 'Просрочены', 'Завершённые', 'Отменённые']) await expect(page.getByRole('tab', { name: tab, exact: true })).toBeVisible()
  for (const [tab, keys, type] of [
    ['В работе', ['draft', 'assembling', 'packed'], 'supply'],
    ['В доставке', ['in_delivery'], 'supply'],
    ['Завершённые', ['done'], 'supply'],
    ['Просрочены', ['wb_expired'], 'order'],
    ['Отменённые', ['wb_cancelled', 'wb_defect', 'ozon_cancelled'], 'order'],
  ]) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expectIds(page, keys.map(key => type === 'order' ? orderId(key) : fixture.supplies[key].id), type)
    await expect(page.getByTestId('fbs-worklist-warehouse')).toHaveCount(0)
    if (tab === 'Отменённые') await expect(page.getByTestId('fbs-worklist-table').getByRole('checkbox')).toHaveCount(0)
  }
})
await run('S2-marketplace-seller-search-empty', async page => {
  await choose(page, 'Маркетплейс', 'Ozon')
  await expectIds(page, [orderId('ozon_new')])
  await choose(page, 'Маркетплейс', 'Wildberries')
  await expectIds(page, newIds.filter(id => id !== orderId('ozon_new')))
  await choose(page, 'Селлер', fixture.sellers[1].name)
  await expectIds(page, sellerBIds)
  await choose(page, 'Селлер', 'Все селлеры')
  await search(page, fixture.orders.wb_new.number)
  await expectIds(page, [orderId('wb_new')])
  await search(page, 'ABSENT-FBS-MAIN-ORDER')
  await expectIds(page, [])
})
await run('S3-ozon-position-fields', async page => {
  const posting = row(page, 'ozon_new')
  await expect(posting).toContainText(fixture.orders.ozon_new.number)
  for (const position of fixture.positions) {
    for (const value of [position.name, position.article]) await expect(posting).toContainText(value)
  }
  // WMS-719: the size column replaces SKU; each Ozon position shows its own size (or a dash) and no SKU is rendered.
  const headerTexts = await page.getByTestId('fbs-worklist-table').locator('thead th').allInnerTexts()
  assert(!headerTexts.includes('SKU'), 'SKU column must be gone from the order list')
  const sizeIndex = headerTexts.indexOf('Размер')
  assert(sizeIndex > 0, 'size column must exist')
  const sizeValues = await posting.locator('td').nth(sizeIndex).locator('[data-fbs-position-content]').allInnerTexts()
  assert.equal(sizeValues.length, fixture.positions.length, 'one size value per Ozon position')
  assert(sizeValues.every(value => value.trim().length > 0), 'every Ozon position shows a size or a dash')
  for (const column of ['Товар', 'Артикул продавца', 'Размер', 'ШК', 'Селлер', 'Маршрут сдачи', 'Отгрузить до']) await expect(page.getByTestId('fbs-worklist-table').getByRole('columnheader', { name: column, exact: true })).toBeVisible()
})
await run('S2-two-wb-warehouses-exact-membership', async page => {
  await choose(page, 'Маркетплейс', 'Wildberries')
  await expectIds(page, newIds.filter(id => id !== orderId('ozon_new')))
  await page.getByTestId('fbs-worklist-warehouse').click()
  await page.getByTestId('fbs-worklist-warehouse-501002').click()
  await expectIds(page, [fixture.second_warehouse_order.id])
  await page.getByTestId('fbs-worklist-warehouse').click()
  await page.getByTestId('fbs-worklist-warehouse-501001').click()
  await expectIds(page, newIds.filter(id => ![orderId('ozon_new'), fixture.second_warehouse_order.id].includes(id)))
  await choose(page, 'Маркетплейс', 'Ozon')
  await expect(page.getByTestId('fbs-worklist-warehouse')).toContainText('Все склады')
  await expectIds(page, [orderId('ozon_new')])
})
await run('S4-hidden-selection-and-loaded-select-all', async page => {
  await row(page, 'wb_new').getByRole('checkbox').check()
  await search(page, fixture.orders.ozon_new.number)
  await expectIds(page, [orderId('ozon_new')])
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
  await page.getByTestId('fbs-worklist-table').locator('thead').getByRole('checkbox').check()
  await expect(bar(page)).toContainText('Выбрано заказов: 2')
  await expect(bar(page).getByRole('button', { name: 'Сформировать поставку', exact: true })).toBeDisabled()
  await page.getByTestId('fbs-selected-open').click()
  const selected = page.getByTestId('fbs-selected-list')
  await expect(selected).toContainText(fixture.orders.wb_new.number)
  await expect(selected).toContainText(fixture.orders.ozon_new.number)
  await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await choose(page, 'Маркетплейс', 'Ozon')
  await expect(bar(page)).toHaveCount(0)
})
await run('S4-not-published-selectable', async page => {
  await expect(row(page, 'wb_unpublished').getByRole('checkbox')).toBeEnabled()
  await row(page, 'wb_unpublished').getByRole('checkbox').check()
  await expect(bar(page).getByRole('button', { name: 'Сформировать поставку', exact: true })).toBeEnabled()
})
await run('S4-selected-dialog-remove-and-clear', async page => {
  await row(page, 'wb_new').getByRole('checkbox').check()
  await row(page, 'ozon_new').getByRole('checkbox').check()
  await page.getByTestId('fbs-selected-open').click()
  const selected = page.getByTestId('fbs-selected-list')
  await selected.getByRole('button', { name: 'Убрать', exact: true }).first().click()
  await expect(selected).not.toContainText(fixture.orders.wb_new.number)
  await expect(selected).toContainText(fixture.orders.ozon_new.number)
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
  await page.getByRole('dialog').getByRole('button', { name: 'Снять всё', exact: true }).click()
  await expect(bar(page)).toHaveCount(0)
  await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(row(page, 'wb_new').getByRole('checkbox')).not.toBeChecked()
  await expect(row(page, 'ozon_new').getByRole('checkbox')).not.toBeChecked()
})
await run('S2-S4-selection-resets-and-warehouse-reset', async page => {
  await row(page, 'wb_new').getByRole('checkbox').check()
  await choose(page, 'Селлер', fixture.sellers[1].name)
  await expectIds(page, sellerBIds)
  await expect(bar(page)).toHaveCount(0)
  await choose(page, 'Селлер', 'Все селлеры')
  await expectIds(page, newIds)
  await row(page, 'wb_new').getByRole('checkbox').check()
  await page.getByTestId('fbs-worklist-warehouse').click()
  await page.getByTestId('fbs-worklist-warehouse-501001').click()
  await expectIds(page, newIds.filter(id => ![orderId('ozon_new'), fixture.second_warehouse_order.id].includes(id)))
  await expect(bar(page)).toHaveCount(0)
  await row(page, 'wb_new').getByRole('checkbox').check()
  await page.getByRole('tab', { name: 'В работе', exact: true }).click()
  await expect(bar(page)).toHaveCount(0)
  await page.getByRole('tab', { name: 'Новые', exact: true }).click()
  await expectIds(page, newIds)
  await expect(page.getByTestId('fbs-worklist-warehouse')).toContainText('Все склады')
})
await run('S4-last-row-remains-clickable-under-selection-panel', async page => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await row(page, 'wb_new').getByRole('checkbox').check()
  const candidates = page.getByTestId('fbs-worklist-table').locator('tbody tr[data-testid^="fbs-order-"]').filter({ has: page.getByRole('checkbox', { checked: false }) })
  const last = candidates.last().getByRole('checkbox')
  await last.scrollIntoViewIfNeeded()
  const checkboxBox = await last.boundingBox()
  const panelBox = await bar(page).boundingBox()
  assert(checkboxBox && panelBox)
  assert(checkboxBox.y + checkboxBox.height <= panelBox.y, 'floating selection panel covers the last selectable row')
  await last.check()
  await expect(bar(page)).toContainText('Выбрано заказов: 2')
})
await run('S4-operator-role', async page => {
  await row(page, 'wb_new').getByRole('checkbox').check()
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
  await expect(page.getByTestId('fbs-orders-sync-wb')).toHaveCount(0)
}, 'operator')
await run('S5-real-preflight-single-wb', async page => {
  await page.getByTestId(`fbs-order-${seed.orders.warehouse_sc[0].wms_order_id}`).getByRole('checkbox').check()
  const checking = page.waitForResponse(response => response.url().includes('/fbs-supplies/preflight') && response.request().method() === 'POST')
  await bar(page).getByRole('button', { name: 'Сформировать поставку', exact: true }).click()
  const response = await checking
  assert(response.ok(), `real preflight failed: ${response.status()}`)
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Новая поставка FBS' })).toBeVisible()
  await expect(page.getByTestId('fbs-create-submit')).toBeEnabled()
  await expect(page.getByRole('radio', { name: 'Склад или сортировочный центр' })).toBeVisible()
  await expect(page.getByRole('radio', { name: 'Пункт выдачи' })).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
})
await run('S6-no-compatible-ozon-supply', async page => {
  await row(page, 'ozon_new').getByRole('checkbox').check()
  await page.getByTestId('fbs-05-add-existing-open').click()
  await expect(page.getByTestId('fbs-05-no-compatible-supply')).toBeVisible()
  await expect(page.getByTestId('fbs-05-add-existing-submit')).toBeDisabled()
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
})
await run('S7-supply-columns-document-url-reload', async page => {
  await page.getByRole('tab', { name: 'В работе', exact: true }).click()
  await expectIds(page, ['draft', 'assembling', 'packed'].map(key => fixture.supplies[key].id), 'supply')
  const table = page.getByTestId('fbs-18-supplies-table')
  assert.equal(await table.getByRole('columnheader').count(), 8)
  for (const header of ['Селлер', 'Склад', 'Заказы / единицы', 'Короба', 'Статус', 'Дата отгрузки', 'Печать']) await expect(table.getByRole('columnheader', { name: header, exact: true })).toBeVisible()
  await page.getByTestId(`fbs-18-supply-${fixture.supplies.draft.id}`).click()
  await expect(page).toHaveURL(new RegExp(`supply_id=${fixture.supplies.draft.id}`))
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.reload()
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByTestId('fbs-workspace').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(page).not.toHaveURL(/supply_id=/)
  await expect(page.getByTestId('fbs-workspace')).toHaveCount(0)
})
await run('S8-missing-upstream-qr-does-not-open-document', async page => {
  await page.getByRole('tab', { name: 'В работе', exact: true }).click()
  await expectIds(page, ['draft', 'assembling', 'packed'].map(key => fixture.supplies[key].id), 'supply')
  const button = page.getByTestId(`fbs-supply-qr-print-${fixture.supplies.packed.id}`)
  await button.click()
  await expect(button).toBeEnabled({ timeout: 30000 })
  await expect(page.getByTestId('fbs-orders-screen').getByRole('alert').filter({ hasText: /WB|QR|поставк/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Проверка перед печатью' })).toHaveCount(0)
  await expect(page.getByTestId('fbs-workspace')).toHaveCount(0)
  await expect(page).not.toHaveURL(/supply_id=/)
})
await run('S9-ozon-cancel-confirmation-only', async page => {
  await row(page, 'ozon_new').getByRole('checkbox').check()
  await page.getByTestId('fbs-orders-cancel-ozon').click()
  await expect(page.getByTestId('fbs-orders-cancel-list')).toContainText(fixture.orders.ozon_new.number)
  await expect(page.getByTestId('fbs-orders-cancel-ozon-confirm')).toBeEnabled()
  await page.getByRole('dialog').getByRole('button', { name: 'Не отменять', exact: true }).click()
  await expect(bar(page)).toContainText('Выбрано заказов: 1')
})
await run('S10-cancelled-wb-entry-marketplace', async page => {
  await page.getByRole('tab', { name: 'Отменённые', exact: true }).click()
  await expect(page.getByTestId('fbs-cancelled-after-pack-open')).toBeVisible()
  await page.getByTestId('fbs-cancelled-after-pack-open').click()
  const dialog = page.getByTestId('fbs-cancelled-after-pack')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('Заказы не найдены', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Следующая страница' })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await choose(page, 'Маркетплейс', 'Ozon')
  await expectIds(page, [orderId('ozon_cancelled')])
  await expect(page.getByTestId('fbs-cancelled-after-pack-open')).toHaveCount(0)
})
await run('S12-independent-metric-seller-and-refresh', async page => {
  await choose(page, 'Селлер', fixture.sellers[1].name)
  await expectIds(page, sellerBIds)
  const loading = page.waitForResponse(response => response.url().includes('/api/fbs/assembly-time?') && new URL(response.url()).searchParams.get('seller_id') === fixture.sellers[0].id)
  await page.getByTestId('fbs-metric-seller').selectOption(fixture.sellers[0].id)
  assert((await loading).ok(), 'actual metric API failed')
  await expectIds(page, sellerBIds)
  await expect(page.getByTestId('fbs-metric-orders')).toHaveText('3')
  await expect(page.getByTestId('fbs-metric-value')).toHaveText('18,0')
  await expect(page.getByTestId('fbs-metric-in12')).toHaveText('33%')
  await expect(page.getByTestId('fbs-metric-in24')).toHaveText('67%')
  const refreshing = page.waitForResponse(response => response.url().includes('/fbs-orders/worklist'))
  await page.getByRole('button', { name: 'Обновить', exact: true }).click()
  assert((await refreshing).ok(), 'actual refresh failed')
  await expectIds(page, sellerBIds)
})
await run('S12-valid-custom-dates-and-month', async page => {
  await page.getByTestId('fbs-metric-preset-month').click()
  await expect(page.getByTestId('fbs-metric-orders')).toHaveText('3')
  await expect(page.getByTestId('fbs-metric-value')).toHaveText('18,0')
  await page.getByTestId('fbs-metric-preset-custom').click()
  const start = new Date(Date.now()-7*24*3600*1000).toISOString().slice(0, 10)
  const end = new Date(Date.now()+24*3600*1000).toISOString().slice(0, 10)
  await page.getByTestId('fbs-metric-range-start').fill(start)
  const loading = page.waitForResponse(response => {
    if (!response.url().includes('/api/fbs/assembly-time?')) return false
    const query = new URL(response.url()).searchParams
    return query.get('from') === `${start}T00:00:00+03:00` && query.get('to') === `${end}T23:59:59+03:00`
  })
  await page.getByTestId('fbs-metric-range-end').fill(end)
  assert((await loading).ok(), 'complete valid custom dates must reach the actual metric API')
  await expect(page.getByTestId('fbs-metric-orders')).toHaveText('3')
  await expect(page.getByTestId('fbs-metric-value')).toHaveText('18,0')
})
await run('S11-export-hidden-selected-wb', async page => {
  await row(page, 'wb_new').getByRole('checkbox').check()
  await search(page, fixture.orders.ozon_new.number)
  await expectIds(page, [orderId('ozon_new')])
  const downloading = page.waitForEvent('download')
  await page.getByTestId('fbs-orders-download-excel').click()
  const download = await downloading
  const file = path.join(evidence, 'selected-wb.xls')
  await download.saveAs(file)
  const html = await readFile(file, 'utf8')
  assert(html.includes(fixture.orders.wb_new.number), 'hidden selected WB order absent from export')
  assert(!html.includes(fixture.orders.ozon_new.number), 'unselected visible order leaked into export')
})
await run('S11-export-ozon-positions-known-defect', async page => {
  await choose(page, 'Маркетплейс', 'Ozon')
  await expectIds(page, [orderId('ozon_new')])
  const downloading = page.waitForEvent('download')
  await page.getByTestId('fbs-orders-download-excel').click()
  const download = await downloading
  const file = path.join(evidence, 'ozon-positions.xls')
  await download.saveAs(file)
  const html = await readFile(file, 'utf8')
  // Owner contract: export must preserve every position and its actual quantity.
  // Do not turn the current hardcoded quantity=1 into an expected value.
  const exported = await page.evaluate(html => {
    const document = new DOMParser().parseFromString(html, 'text/html')
    const headers = [...document.querySelectorAll('thead th')].map(cell => cell.textContent)
    return [...document.querySelectorAll('tbody tr')].map(row => Object.fromEntries([...row.querySelectorAll('td')].map((cell, index) => [headers[index], cell.textContent])))
  }, html)
  assert.deepEqual(exported.map(row => ({ name: row['Наименование'], article: row['Артикул продавца'], quantity: Number(row['Количество']) })).sort((a,b) => a.name.localeCompare(b.name)), fixture.positions.map(({name, article, quantity}) => ({name, article, quantity})).sort((a,b) => a.name.localeCompare(b.name)), 'Every Ozon position and actual quantity must survive export')
  assert.equal(exported.reduce((sum, row) => sum + Number(row['Количество']), 0), 5)
})
await run('S1-S12-arriving-order-refresh-and-no-sync-duplicate', async (page, { context, token }) => {
  const emulator = process.env.FBS_MAIN_EMULATOR || 'http://127.0.0.1:28081'
  assert(['localhost', '127.0.0.1'].includes(new URL(emulator).hostname))
  const response = await context.request.post(`${emulator}/__admin/orders?seller=seller_a&count=1&warehouse_id=501001&chrt_id=111001`, { headers: { 'X-Admin-Token': 'fbs-e2e-admin' } })
  assert(response.ok(), `emulator create order: ${response.status()}`)
  const created = await response.json()
  assert.equal(created.created, 1)
  const externalId = created.orders[0].id
  const headers = { Authorization: `Bearer ${token}` }
  async function synchronize() {
    const response = await context.request.post(`${root}/api/operations/fbs-orders/sync`, { headers, data: { seller_id: seed.seller_id } })
    assert.equal(response.status(), 202)
    const job = await response.json()
    await expect.poll(async () => {
      const response = await context.request.get(`${root}/api/operations/background-jobs/${job.id}`, { headers })
      assert(response.ok())
      const body = await response.json()
      assert.notEqual(body.status, 'failed', 'real synchronization background job failed')
      return body.status
    }, { timeout: 120000, intervals: [500, 1000] }).toBe('done')
  }
  await synchronize()
  const worklist = await context.request.get(`${root}/api/operations/fbs-orders/worklist?seller_id=${seed.seller_id}&status_group=new&limit=200`, { headers })
  assert(worklist.ok())
  const matches = (await worklist.json()).items.filter(order => String(order.wb_order_id) === String(externalId))
  assert.equal(matches.length, 1, 'one marketplace order must become one WMS record')
  const arrived = matches[0].id
  newIds.push(arrived)
  await page.getByRole('button', { name: 'Обновить', exact: true }).click()
  await expectIds(page, newIds)
  await expect(page.getByTestId(`fbs-order-${arrived}`)).toContainText(String(externalId))
  await synchronize()
  await page.getByRole('button', { name: 'Обновить', exact: true }).click()
  await expectIds(page, newIds)
  assert.equal(await page.getByTestId(`fbs-order-${arrived}`).count(), 1)
})
await run('S5-S6-real-create-and-add-existing-wb', async (page, { context, token }) => {
  const [first, second] = seed.orders.warehouse_sc.map(order => order.wms_order_id)
  await page.getByTestId(`fbs-order-${first}`).getByRole('checkbox').check()
  await bar(page).getByRole('button', { name: 'Сформировать поставку', exact: true }).click()
  await expect(page.getByTestId('fbs-create-submit')).toBeEnabled()
  const creating = page.waitForResponse(response => response.url().endsWith('/fbs-supplies/from-orders') && response.request().method() === 'POST')
  await page.getByTestId('fbs-create-submit').click()
  const createdResponse = await creating
  assert(createdResponse.ok(), `actual creation failed: ${createdResponse.status()}`)
  const workspace = await createdResponse.json()
  const supplyId = workspace.supply.id
  assert.deepEqual(workspace.orders.map(order => order.id), [first])
  newIds.splice(newIds.indexOf(first), 1)
  await expect(page).toHaveURL(new RegExp(`supply_id=${supplyId}`))
  await expect(page.getByTestId('fbs-workspace')).toBeVisible()
  await page.getByTestId('fbs-workspace').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByRole('tab', { name: 'Новые', exact: true }).click()
  await expectIds(page, newIds.filter(id => id !== first))
  await expect(bar(page)).toHaveCount(0)
  await page.getByTestId(`fbs-order-${second}`).getByRole('checkbox').check()
  await page.getByTestId('fbs-05-add-existing-open').click()
  await page.getByTestId('fbs-05-existing-supply-select').click()
  // Choose by supply name from the creation response; no mocked compatibility.
  await page.getByRole('option').filter({ hasText: workspace.supply.name }).click()
  const adding = page.waitForResponse(response => response.url().endsWith(`/fbs-supplies/${supplyId}/orders/batch`) && response.request().method() === 'POST')
  await page.getByTestId('fbs-05-add-existing-submit').click()
  const addedResponse = await adding
  assert(addedResponse.ok(), `actual add failed: ${addedResponse.status()}`)
  const added = await addedResponse.json()
  assert.deepEqual(added.orders.map(order => order.id).sort(), [first, second].sort())
  newIds.splice(newIds.indexOf(second), 1)
  await expect(page).toHaveURL(new RegExp(`supply_id=${supplyId}`))
  await page.getByTestId('fbs-workspace').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await page.getByRole('tab', { name: 'Новые', exact: true }).click()
  await expectIds(page, newIds.filter(id => ![first, second].includes(id)))
  await expect(bar(page)).toHaveCount(0)
  const reloaded = await context.request.get(`${root}/api/operations/fbs-supplies/${supplyId}/workspace`, { headers: { Authorization: `Bearer ${token}` } })
  assert(reloaded.ok())
  assert.deepEqual((await reloaded.json()).orders.map(order => order.id).sort(), [first, second].sort(), 'committed API readback must contain both orders exactly once')
  createdWbSupplyId = supplyId
})
await run('S8-ready-wb-cargo-qr-preview-and-copies', async (page, { context, token }) => {
  assert(createdWbSupplyId, 'Dependency: real create/add scenario must first produce a committed WB supply')
  const supplyId = createdWbSupplyId
  // Prepare an actual upstream WB cargo-place QR through WMS. The main-table
  // action must download and preview that real stored asset without opening a document.
  const cargo = await context.request.post(`${root}/api/operations/fbs-supplies/${supplyId}/cargo-places`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { count: 1, boxes: [{ client_id: 'main-ci-box', length_mm: 100, width_mm: 100, height_mm: 100, weight_g: 500 }], idempotency_key: `main-qr-${supplyId}` },
  })
  assert.equal(cargo.status(), 201, 'real WB cargo-place preparation failed')
  const places = (await cargo.json()).cargo_places
  assert.equal(places.length, 1)
  assert.equal(places[0].qr_asset.status, 'ready')
  await page.getByRole('tab', { name: 'В работе', exact: true }).click()
  await page.getByTestId(`fbs-supply-qr-print-${supplyId}`).click()
  const preview = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: 'Проверка перед печатью', exact: true }) })
  await expect(preview).toBeVisible()
  await expect(preview.getByText('Готово 1', { exact: true })).toBeVisible()
  await expect(preview.getByRole('button', { name: 'Печать', exact: true })).toBeEnabled()
  await expect(page.getByTestId('fbs-workspace')).toHaveCount(0)
  await expect(page).not.toHaveURL(/supply_id=/)
  await preview.getByTestId('fbs-print-preview-copies').locator('input').fill('99')
  await preview.getByTestId('fbs-print-preview-copies').locator('input').blur()
  await expect(preview.getByTestId('fbs-print-preview-copies').locator('input')).toHaveValue('99')
  await preview.getByTestId('fbs-print-preview-copies').locator('input').fill('1')
  await preview.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(preview).toHaveCount(0)
})
await run('S5-S7-two-sellers-two-wb-warehouses-common-assembly', async (page, { context, token }) => {
  const selected = [seed.orders.pvz[0].wms_order_id, fixture.second_warehouse_order.id]
  for (const id of selected) await page.getByTestId(`fbs-order-${id}`).getByRole('checkbox').check()
  const creations = []
  page.on('response', response => {
    if (response.url().endsWith('/fbs-supplies/from-orders') && response.request().method() === 'POST') creations.push(response.json())
  })
  await bar(page).getByRole('button', { name: 'Сформировать поставку', exact: true }).click()
  const dialog = page.getByTestId('fbs-group-create-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('tr[data-testid^="fbs-group-create-row-"]')).toHaveCount(2)
  await expect(page.getByTestId('fbs-group-create-submit')).toBeEnabled()
  const creatingTask = page.waitForResponse(response => response.url().endsWith('/fbs-assembly-tasks') && response.request().method() === 'POST')
  await page.getByTestId('fbs-group-create-submit').click()
  const taskResponse = await creatingTask
  assert(taskResponse.ok(), `common assembly task failed: ${taskResponse.status()}`)
  const task = await taskResponse.json()
  const documents = await Promise.all(creations)
  assert.equal(documents.length, 2)
  assert.deepEqual(documents.flatMap(document => document.orders.map(order => order.id)).sort(), selected.sort())
  assert.deepEqual(documents.map(document => document.supply.seller.id).sort(), fixture.sellers.slice(0,2).map(seller => seller.id).sort())
  assert.deepEqual(documents.map(document => document.supply.wb_warehouse.id).sort(), [501001, 501002])
  assert(documents.every(document => document.supply.marketplace === 'wb'))
  const supplyIds = documents.map(document => document.supply.id).sort()
  assert.deepEqual(task.supplies.map(supply => supply.id).sort(), supplyIds)
  for (const id of selected) newIds.splice(newIds.indexOf(id), 1)
  const assembly = page.getByTestId('fbs-assembly')
  await expect(assembly).toBeVisible()
  assert.deepEqual(new URL(page.url()).searchParams.get('supply_ids').split(',').sort(), supplyIds)
  await page.reload()
  await expect(assembly).toBeVisible()
  await assembly.getByRole('tab', { name: 'Состав', exact: true }).click()
  for (const supplyId of supplyIds) await expect(page.getByTestId(`fbs-assembly-composition-supply-${supplyId}`)).toBeVisible()
  await assembly.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(page).not.toHaveURL(/supply_ids=/)
  await expect(page.getByTestId(`fbs-assembly-task-${task.id}`)).toBeVisible()
  for (const supplyId of supplyIds) assert.equal(await page.getByTestId(`fbs-18-supply-${supplyId}`).count(), 1, 'nested supply must appear once')
  const taskRead = await context.request.get(`${root}/api/operations/fbs-assembly-tasks`, { headers: { Authorization: `Bearer ${token}` } })
  assert(taskRead.ok())
  const matches = (await taskRead.json()).items.filter(item => item.id === task.id)
  assert.equal(matches.length, 1)
  assert.deepEqual(matches[0].supplies.map(supply => supply.id).sort(), supplyIds)
})
await browser.close()
await writeFile(path.join(evidence, 'results.json'), JSON.stringify(results, null, 2))
for (const result of results) console.log(`${result.status.toUpperCase()} ${result.name}${result.error ? `\n${result.error}` : ''}`)
if (results.some(result => result.status === 'failed')) process.exitCode = 1
