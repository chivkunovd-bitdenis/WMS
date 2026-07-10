import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-NEW-001 — FF складской каталог: все товары селлеров, остатки по движениям.
// Given: FF admin, есть товары селлеров, один товар не принимался на склад; When: открывает «Каталог»;
// Then: видны все товары селлеров; у принятых остаток равен actual_qty, у непринятых — 0.
test('ff products: filter by seller and sort by name/quantity', async ({ page }) => {
  const email = `e2e-ff-products-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await openFulfillmentRegistration(page)

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Products')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await expect(page.getByTestId('dashboard')).toBeVisible()

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  expect(regToken).toBeTruthy()
  const h = { Authorization: `Bearer ${regToken}` }

  async function apiPost(path: string, data: Record<string, unknown>) {
    const res = await page.request.post(`/api${path}`, { headers: h, data })
    if (!res.ok()) {
      throw new Error(`POST ${path} failed: ${res.status()} ${await res.text()}`)
    }
    return res
  }

  async function apiPatch(path: string, data: Record<string, unknown>) {
    const res = await page.request.patch(`/api${path}`, { headers: h, data })
    if (!res.ok()) {
      throw new Error(`PATCH ${path} failed: ${res.status()} ${await res.text()}`)
    }
    return res
  }

  // Seed: 2 sellers + products; one product stays private-only with no FF movement.
  const sellerA = (await (await apiPost('/sellers', { name: 'E2E Seller A' })).json()) as { id: string }
  const sellerB = (await (await apiPost('/sellers', { name: 'E2E Seller B' })).json()) as { id: string }

  const skuA = `e2e-ff-a-${Date.now()}`
  const skuB = `e2e-ff-b-${Date.now()}`
  const skuPrivate = `e2e-ff-private-${Date.now()}`
  const prodA = (await (
    await apiPost('/products', {
      name: 'Alpha product',
      sku_code: skuA,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerA.id,
    })
  ).json()) as { id: string }
  const prodB = (await (
    await apiPost('/products', {
      name: 'Beta product',
      sku_code: skuB,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerB.id,
    })
  ).json()) as { id: string }
  await apiPost('/products', {
    name: 'Private only product',
    sku_code: skuPrivate,
    length_mm: 1,
    width_mm: 1,
    height_mm: 1,
    seller_id: sellerA.id,
  })

  // Put different stock totals via inbound receive so sorting by остаток is meaningful.
  const whCode = `e2e-wh-${Date.now()}`
  const wh = (await (await apiPost('/warehouses', { name: 'E2E WH', code: whCode })).json()) as { id: string }
  const loc = (await (await apiPost(`/warehouses/${wh.id}/locations`, { code: 'A-01' })).json()) as {
    id: string
  }

  async function inboundReceive(
    productId: string,
    skuCode: string,
    expectedQty: number,
    actualQty: number,
  ) {
    const createReq = await apiPost('/operations/inbound-intake-requests', {
      warehouse_id: wh.id,
      planned_delivery_date: new Date().toISOString().slice(0, 10),
    })
    const req = (await createReq.json()) as { id: string }
    const addLineRes = await apiPost(`/operations/inbound-intake-requests/${req.id}/lines`, {
      product_id: productId,
      expected_qty: expectedQty,
    })
    const line = (await addLineRes.json()) as { id: string }
    await apiPost(`/operations/inbound-intake-requests/${req.id}/submit`, {})
    const inboundBox = await apiPost(`/operations/inbound-intake-requests/${req.id}/boxes`, {})
    await apiPatch(`/operations/inbound-intake-requests/${req.id}/lines/${line.id}`, {
      storage_location_id: loc.id,
    })
    const inboundBoxBody = (await inboundBox.json()) as { id: string; internal_barcode: string }
    const { fulfillInboundViaBoxScans } = await import('./inbound-boxes-helpers')
    await fulfillInboundViaBoxScans(
      page.request,
      h,
      req.id,
      [inboundBoxBody],
      skuCode,
      [actualQty],
    )
    await apiPost(`/operations/inbound-intake-requests/${req.id}/verify`, {})
    await apiPost(`/operations/inbound-intake-requests/${req.id}/post`, {})
  }

  await inboundReceive(prodA.id, skuA, 10, 2)
  await inboundReceive(prodB.id, skuB, 10, 5)

  // Reload so App re-fetches sellers list for the filter dropdown.
  await page.reload()
  await expect(page.getByTestId('dashboard')).toBeVisible()

  // Go to FF products screen
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-products-table')).toBeVisible()

  // Filter by seller A
  await page.getByTestId('ff-products-seller-filter').click()
  const sellerListbox = page.getByRole('listbox')
  await expect(sellerListbox).toBeVisible()
  await sellerListbox.getByText('E2E Seller A', { exact: true }).click()
  await expect(page.getByTestId('ff-product-row')).toHaveCount(2)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuA)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuPrivate)
  await expect(page.getByTestId(`ff-product-unpacked-${prodA.id}`)).toHaveText('2')

  // Switch to All
  await page.getByTestId('ff-products-seller-filter').click()
  await expect(sellerListbox).toBeVisible()
  await sellerListbox.getByText('Все', { exact: true }).click()
  await expect(page.getByTestId('ff-product-row')).toHaveCount(3)

  // TC-NEW-002 — поиск по артикулу (SKU) и названию
  await page.getByTestId('ff-products-search').fill('Private only')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(1)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuPrivate)

  await page.getByTestId('ff-products-search').fill(skuA)
  await expect(page.getByTestId('ff-product-row')).toHaveCount(1)
  await expect(page.getByTestId('ff-products-table')).toContainText('Alpha product')

  await page.getByTestId('ff-products-search').fill('zzz-no-match-xyz')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(0)
  await expect(page.getByTestId('ff-products-search-empty')).toBeVisible()

  await page.getByTestId('ff-products-search').fill('')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(3)

  // Sort by quantity desc: first row should be product B (qty 5)
  await page.getByTestId('ff-products-sort-quantity').click()
  await page.getByTestId('ff-products-sort-quantity').click()
  const firstSkuAfterQty = await page.getByTestId('ff-product-row').first().locator('td').nth(1).innerText()
  expect(firstSkuAfterQty).toContain(skuB)

  // Sort by name asc: Alpha first
  await page.getByTestId('ff-products-sort-name').click()
  const firstNameAfterName = await page.getByTestId('ff-product-row').first().locator('td').nth(6).innerText()
  expect(firstNameAfterName).toContain('Alpha')

  // Photo cell exists (even if WB photo missing in mocks): first column rendered and has avatar element.
  await expect(page.getByTestId('ff-product-row').first().locator('td').first()).toBeVisible()
})

// TC-NEW-PKG-04 — FF редактирует ТЗ упаковки в каталоге товаров.
test('ff products: edit packaging instructions in catalog', async ({ page }) => {
  const email = `e2e-ff-pkg-tz-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF TZ')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${regToken}`, 'Content-Type': 'application/json' }
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'
  const sku = `SKU-TZ-${Date.now()}`

  const wh = await page.request.post(`${e2eApi}/warehouses`, {
    headers: h,
    data: JSON.stringify({ name: 'WH', code: `wh-tz-${Date.now()}` }),
  })
  const whId = String(((await wh.json()) as { id: string }).id)
  const pr = await page.request.post(`${e2eApi}/products`, {
    headers: h,
    data: JSON.stringify({ name: 'TZ Product', sku_code: sku, length_mm: 1, width_mm: 1, height_mm: 1 }),
  })
  const productId = String(((await pr.json()) as { id: string }).id)

  const baseIn = `${e2eApi}/operations/inbound-intake-requests`
  const inbound = await page.request.post(baseIn, {
    headers: h,
    data: JSON.stringify({ warehouse_id: whId }),
  })
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: h,
    data: JSON.stringify({ product_id: productId, expected_qty: 1 }),
  })
  await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: h })
  const inboundBox = await page.request.post(`${baseIn}/${inboundId}/boxes`, { headers: h })
  const inboundBoxBody = (await inboundBox.json()) as { id: string; internal_barcode: string }
  const { fulfillInboundViaBoxScans } = await import('./inbound-boxes-helpers')
  await fulfillInboundViaBoxScans(page.request, h, inboundId, [inboundBoxBody], sku, [1])
  await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: h })
  await page.request.post(`${baseIn}/${inboundId}/post`, { headers: h })

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId(`ff-packaging-status-${productId}`)).toContainText('Нет ТЗ')

  await page.getByTestId(`ff-packaging-edit-${productId}`).click()
  await expect(page.getByTestId('ff-packaging-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-packaging-print')).toBeVisible()
  await page.getByTestId('ff-packaging-text').fill('E2E: пакет + бирка')
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes('/packaging-instructions') &&
        r.status() >= 200 &&
        r.status() < 300,
    ),
    page.getByTestId('ff-packaging-save').click(),
  ])
  await expect(page.getByTestId(`ff-packaging-status-${productId}`)).toContainText('Заполнено')
})

// TC-NEW-MAN-01 — FF создаёт товар вручную; бейдж «Вручную» пока нет карточки WB.
// Given: FF admin и селлер; When: «Создать товар» без габаритов;
// Then: товар в каталоге с «Вручную», поиск по ШК. Бейдж снимается после WB sync/link по тому же ШК.
test('ff products: manual create shows manual badge', async ({ page }) => {
  const email = `e2e-ff-manual-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Manual')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${regToken}` }
  const seller = (await (
    await page.request.post('/api/sellers', { headers: h, data: { name: 'Manual Seller' } })
  ).json()) as { id: string }

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()

  await page.getByTestId('ff-products-create').click()
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible()
  await page.getByTestId('ff-manual-product-seller').click()
  await page.getByRole('listbox').getByText('Manual Seller', { exact: true }).click()
  const sku = `MAN-E2E-${Date.now()}`
  const barcode = `204${String(Date.now()).slice(-10)}`
  await page.getByTestId('ff-manual-product-name').fill('Ручной E2E товар')
  await page.getByTestId('ff-manual-product-sku').fill(sku)
  await page.getByTestId('ff-manual-product-barcode').fill(barcode)
  await page.getByTestId('ff-manual-product-size').fill('46')
  await page.getByTestId('ff-manual-product-tz').fill('E2E ТЗ вручную')

  await Promise.all([
    waitForPostOk(page, '/api/products'),
    page.getByTestId('ff-manual-product-submit').click(),
  ])

  await expect(page.getByTestId('ff-products-table')).toContainText(sku)
  const row = page.getByTestId('ff-product-row').filter({ hasText: sku })
  await expect(row.getByText('Вручную')).toBeVisible()
  await page.getByTestId('ff-products-search').fill(barcode)
  await expect(page.getByTestId('ff-product-row')).toHaveCount(1)
  void seller
})

// TC-NEW-MAN-02 — FF загружает Excel ТЗ: preview → apply → товары с ТЗ и бейджем.
// TC-NEW-PRODUCT-TZ-01 — preview показывает заявленное количество, apply ставит его в сортировку.
// TC-NEW-PRODUCT-TZ-02 — повтор файла защищён backend-идемпотентностью (API regression test).
// TC-NEW-TZ-STOCK-002 — во время apply нельзя сменить селлера/файл или закрыть диалог через Cancel/ESC.
// Given: FF admin, селлер, xlsx с объединённым ТЗ, лист называется произвольно (не «ТЗ Шаблон»);
// When: «Загрузить Excel» и Применить;
// Then: импорт находит нужный лист по структуре колонок (имя листа не важно), товары в каталоге,
// ТЗ заполнено, бейдж «Вручную».
test('ff products: import tz xlsx creates manual products with packaging', async ({ page }) => {
  const email = `e2e-ff-tz-imp-${Date.now()}@example.com`
  const password = 'password123'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF TZ Imp')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${regToken}` }
  await page.request.post('/api/sellers', { headers: h, data: { name: 'TZ Seller' } })
  const warehouse = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'TZ Warehouse', code: `tz-wh-${Date.now()}` },
  })
  expect(warehouse.ok()).toBeTruthy()
  const warehouseId = String(((await warehouse.json()) as { id: string }).id)

  // Build minimal xlsx in browser via API seed is easier: use backend fixture through request
  // with a tiny zip-based xlsx generated by Node Buffer — use page.evaluate + fetch to apply
  // after uploading a file created from base64 of a known-good minimal workbook.
  const { execFileSync } = await import('node:child_process')
  const path = await import('node:path')
  const fs = await import('node:fs')
  const os = await import('node:os')
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tz-xlsx-'))
  const xlsxPath = path.join(tmp, 'tz.xlsx')
  const badXlsxPath = path.join(tmp, 'tz-invalid.xlsx')
  const py = `
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.title = "Мой произвольный лист"
ws.append(["Артикул продавца","Фото","Размер","Штрихкод","Информация для этикетки","Пожелания/Инструкция по обработке, упаковке и фасовке","Кол/во, заявленное клиентом"])
ws.append(["E2E-ART", None, 46, None, "2039000000001", None, 40])
ws.append(["E2E-ART", None, 48, None, "2039000000002", None, 2])
ws["F2"] = "E2E merged TZ"
ws.merge_cells("F2:F3")
wb.save(${JSON.stringify(xlsxPath)})
bad = Workbook()
bad_ws = bad.active
bad_ws.title = "Ошибочное количество"
bad_ws.append(["Артикул продавца","Фото","Размер","Штрихкод","Информация для этикетки","Пожелания/Инструкция по обработке, упаковке и фасовке","Кол/во, заявленное клиентом"])
bad_ws.append(["E2E-BAD", None, 46, None, "2039000000099", "TZ", -1])
bad.save(${JSON.stringify(badXlsxPath)})
`
  execFileSync('python3', ['-c', py], { stdio: 'pipe' })

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await page.getByTestId('ff-products-import-tz').click()
  await expect(page.getByTestId('ff-tz-import-dialog')).toBeVisible()
  await page.getByTestId('ff-tz-import-seller').click()
  await page.getByRole('listbox').getByText('TZ Seller', { exact: true }).click()

  await page.getByTestId('ff-tz-import-file').locator('input[type="file"]').setInputFiles(xlsxPath)
  await expect(page.getByTestId('ff-tz-import-summary')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('ff-tz-import-summary')).toContainText('создать 2')
  await expect(page.getByTestId('ff-tz-import-summary')).toContainText('заявлено 42')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('40')

  let releaseApply!: () => void
  const holdApply = new Promise<void>((resolve) => {
    releaseApply = resolve
  })
  await page.route('**/products/import-tz/apply', async (route) => {
    await holdApply
    await route.continue()
  })
  const applyResponse = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/products/import-tz/apply') &&
      r.status() >= 200 &&
      r.status() < 300,
  )
  await page.getByTestId('ff-tz-import-apply').click()
  await expect(
    page.getByTestId('ff-tz-import-seller').getByRole('combobox'),
  ).toHaveAttribute('aria-disabled', 'true')
  await expect(page.getByTestId('ff-tz-import-file')).toBeDisabled()
  await expect(page.getByTestId('ff-tz-import-cancel')).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('ff-tz-import-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-products-import-notice')).toHaveCount(0)
  releaseApply()
  await applyResponse
  await page.unroute('**/products/import-tz/apply')

  await expect(page.getByTestId('ff-products-import-notice')).toBeVisible()
  await expect(page.getByTestId('ff-products-import-notice')).toContainText(
    'добавлено в сортировку: 42',
  )
  await expect(page.getByTestId('ff-products-table')).toContainText('E2E-ART')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(2)
  await expect(page.getByText('Вручную').first()).toBeVisible()
  await page.getByTestId('ff-products-search').fill('2039000000001')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(1)
  const balances = await page.request.get('/api/operations/inventory-balances/summary', {
    headers: h,
    params: { warehouse_id: warehouseId },
  })
  const importedTotal = (
    (await balances.json()) as { quantity_in_sorting: number }[]
  ).reduce((total, row) => total + row.quantity_in_sorting, 0)
  expect(importedTotal).toBe(42)

  await page.getByTestId('ff-products-import-tz').click()
  await page.getByTestId('ff-tz-import-seller').click()
  await page.getByRole('listbox').getByText('TZ Seller', { exact: true }).click()
  await page
    .getByTestId('ff-tz-import-file')
    .locator('input[type="file"]')
    .setInputFiles(badXlsxPath)
  await expect(page.getByTestId('ff-tz-import-summary')).toContainText('ошибок 1')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText(
    'Количество не может быть отрицательным',
  )
  await expect(page.getByTestId('ff-tz-import-apply')).toBeDisabled()
})

// TC-NEW-SELLER-01 — FF создаёт селлера прямо из каталога товаров (только название, без входа/почты).
// Given: FF admin на экране «Каталог»; When: жмёт «Создать селлера», вводит название, сохраняет;
// Then: диалог закрывается, показывается уведомление, новый селлер сразу виден в фильтре по селлеру
// и в выпадающем списке при создании товара — без перезагрузки страницы.
// Negative: пустое название не отправляется, показывается ошибка валидации.
test('ff products: create seller from catalog and use it right away for a product', async ({ page }) => {
  const email = `e2e-ff-seller-create-${Date.now()}@example.com`
  const password = 'password123'
  const sellerName = `E2E New Seller ${Date.now()}`

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Seller Create')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  await expect(page.getByTestId('dashboard')).toBeVisible()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()

  // Negative: empty name is rejected without an API call.
  await page.getByTestId('ff-products-create-seller').click()
  await expect(page.getByTestId('ff-seller-create-dialog')).toBeVisible()
  await page.getByTestId('ff-seller-create-submit').click()
  await expect(page.getByTestId('ff-seller-create-error')).toContainText('Укажите название')

  // Happy path: just a name, no email/login required.
  await page.getByTestId('ff-seller-create-name').fill(sellerName)
  await Promise.all([
    waitForPostOk(page, '/api/sellers'),
    page.getByTestId('ff-seller-create-submit').click(),
  ])
  await expect(page.getByTestId('ff-seller-create-dialog')).toBeHidden()
  await expect(page.getByTestId('ff-products-import-notice')).toContainText(sellerName)

  // Available immediately in the catalog seller filter (no reload).
  await page.getByTestId('ff-products-seller-filter').click()
  await expect(page.getByRole('listbox').getByText(sellerName, { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')

  // Available immediately when creating a product (same seller list, same "just a seller" entity).
  await page.getByTestId('ff-products-create').click()
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible()
  await page.getByTestId('ff-manual-product-seller').click()
  await page.getByRole('listbox').getByText(sellerName, { exact: true }).click()
  const sku = `SELLER-E2E-${Date.now()}`
  await page.getByTestId('ff-manual-product-name').fill('Товар нового селлера')
  await page.getByTestId('ff-manual-product-sku').fill(sku)
  await Promise.all([
    waitForPostOk(page, '/api/products'),
    page.getByTestId('ff-manual-product-submit').click(),
  ])
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeHidden()
  await expect(page.getByTestId('ff-products-table')).toContainText(sku)
})
