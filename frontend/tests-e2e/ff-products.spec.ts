import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import { openFulfillmentRegistration } from './auth-flow'

// TC-CAT-01 — каталог FF показывает карточки товаров и краткий фактический остаток.
// Given: FF admin и товары разных селлеров; When: открывает «Каталог»;
// Then: название, артикул продавца, SKU, ШК, размер и остаток разнесены по отдельным колонкам;
// negative: нет устаревших технических колонок сортировки и упаковки.
test('ff products: catalog separates product fields and shows compact stock', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
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

  // Seed: 2 sellers + products; catalog карточки не зависят от складского движения.
  const sellerA = (await (await apiPost('/sellers', { name: 'E2E Seller A' })).json()) as { id: string }
  const sellerB = (await (await apiPost('/sellers', { name: 'E2E Seller B' })).json()) as { id: string }

  const skuA = 'SKU-CAT-A'
  const skuB = 'SKU-CAT-B'
  const skuPrivate = 'SKU-CAT-PRIVATE'
  const barcodeA = '2031111111177'
  const barcodeB = '2031111111188'
  await apiPost('/products', {
    name: 'Alpha product',
    sku_code: skuA,
    length_mm: 1,
    width_mm: 1,
    height_mm: 1,
    seller_id: sellerA.id,
    wb_vendor_code: 'ART-A',
    wb_barcode: barcodeA,
    wb_size: '46',
    packaging_instructions: 'Пакет + стикер',
  })
  await apiPost('/products', {
    name: 'Beta product',
    sku_code: skuB,
    length_mm: 1,
    width_mm: 1,
    height_mm: 1,
    seller_id: sellerB.id,
    wb_vendor_code: 'ART-B',
    wb_barcode: barcodeB,
    wb_size: '48',
  })
  await apiPost('/products', {
    name: 'Private only product',
    sku_code: skuPrivate,
    length_mm: 1,
    width_mm: 1,
    height_mm: 1,
    seller_id: sellerA.id,
  })

  // Reload so App re-fetches sellers list for the catalog dialogs.
  await page.reload()
  await expect(page.getByTestId('dashboard')).toBeVisible()

  // Go to FF products screen
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await expect(page.getByTestId('ff-products-table')).toBeVisible()
  const tableHead = page.getByTestId('ff-products-table').locator('thead')
  await expect(tableHead).toContainText('Название')
  await expect(tableHead).toContainText('Артикул продавца')
  await expect(tableHead).toContainText('SKU')
  await expect(tableHead).toContainText('ШК')
  await expect(tableHead).toContainText('Размер')
  await expect(tableHead).toContainText('Селлер')
  await expect(tableHead).toContainText('Остаток')
  await expect(tableHead).toContainText('ТЗ')
  await expect(tableHead).toContainText('ЧЗ')
  await expect(tableHead).toContainText('Резервы')
  await expect(tableHead).not.toContainText('WB/nmId')
  await expect(tableHead).not.toContainText('Распределение')
  await expect(tableHead).not.toContainText('Сортировка')
  await expect(tableHead).not.toContainText('Не упаковано')
  await expect(tableHead).not.toContainText('Упаковано')
  await expect(tableHead).not.toContainText('Технический резерв')
  await expect(page.getByTestId('ff-products-table')).not.toContainText('Сортировка')
  await expect(page.getByTestId('ff-products-table')).not.toContainText('Не упаковано')
  await expect(page.getByTestId('ff-products-table')).not.toContainText('Упаковано')
  await expect(page.getByTestId('ff-products-table')).not.toContainText('Технический резерв')
  await expect(page.getByTestId('ff-catalog-search')).toBeVisible()
  await expect(page.getByTestId('ff-catalog-seller-filter')).toBeVisible()
  await expect(page.getByText('Вручную', { exact: true })).toHaveCount(0)
  await expect(page.getByTestId('ff-product-row')).toHaveCount(3)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuA)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuB)
  await expect(page.getByTestId('ff-products-table')).toContainText(skuPrivate)

  const alphaRow = page.getByTestId('ff-product-row').filter({ hasText: skuA })
  // Нулевая колонка — чекбокс массового выбора, поэтому фото идёт первым, а не нулевым.
  await expect(alphaRow.locator('td').nth(2)).toContainText('Alpha product')
  await expect(alphaRow.locator('td').nth(2)).not.toContainText('ART-A')
  await expect(alphaRow.locator('td').nth(2)).not.toContainText('46')
  await expect(alphaRow.locator('td').nth(3)).toContainText('ART-A')
  await expect(alphaRow.locator('td').nth(4)).toContainText(skuA)
  await expect(alphaRow.locator('td').nth(5)).toContainText(barcodeA)
  await expect(alphaRow.getByTestId(/ff-catalog-stock-in-storage-/)).toHaveText('В ячейках 0')
  await expect(alphaRow.getByTestId(/ff-catalog-stock-on-hand-/)).toHaveText('На ФФ 0')
  await expect(alphaRow.getByTestId(/ff-catalog-stock-free-fbo-/)).toHaveText('Свободный FBO 0')
  // Размер ищем по строке, а не по номеру колонки: порядок колонок каталога
  // меняется (WB/nmId уехал в конец, чтобы липкая колонка действий не перекрывала
  // соседнюю), и позиционная проверка ломается при каждой перестановке.
  await expect(alphaRow).toContainText('46')

  // Photo cell exists even if WB photo is missing in mocks.
  await expect(page.getByTestId('ff-product-row').first().locator('td').nth(1)).toBeVisible()
  // Чекбокс массового выбора — первым в строке, им отмечают товары для простановки
  // остатка FBS пачкой.
  await expect(
    page.getByTestId('ff-product-row').first().locator('td').nth(0).locator('input[type="checkbox"]'),
  ).toBeVisible()
})

// TC-CAT-03 — строка каталога ведёт в карточку кодов маркировки одной иконкой.
// Given: у товара есть доступные КМ; When: FF admin открывает каталог;
// Then: видны признак ЧЗ и иконка кодов со счётчиком; клик ведёт в карточку товара ЧЗ.
test('ff products: marking icon shows count and opens honest sign product card', async ({ page }) => {
  const email = `e2e-ff-catalog-chz-${Date.now()}@example.com`
  const password = 'password123'
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000'

  await page.goto('/')
  await openFulfillmentRegistration(page)
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Catalog CHZ')
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email)
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password)
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])

  const regToken = (await page.evaluate(() => localStorage.getItem('wms_token_ff'))) ?? ''
  const h = { Authorization: `Bearer ${regToken}`, 'Content-Type': 'application/json' }
  const bearer = { Authorization: `Bearer ${regToken}` }
  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: h,
    data: JSON.stringify({ name: 'E2E Catalog ChZ Seller' }),
  })
  expect(sellerRes.ok()).toBeTruthy()
  const sellerId = String(((await sellerRes.json()) as { id: string }).id)
  const sku = `CAT-CHZ-${Date.now()}`
  const productRes = await page.request.post(`${e2eApi}/products`, {
    headers: h,
    data: JSON.stringify({
      name: 'Catalog ChZ Product',
      sku_code: sku,
      length_mm: 1,
      width_mm: 1,
      height_mm: 1,
      seller_id: sellerId,
      requires_honest_sign: true,
    }),
  })
  expect(productRes.ok()).toBeTruthy()
  const productId = String(((await productRes.json()) as { id: string }).id)

  const gtin = '00000000007777'
  const cis1 = `01${gtin}21${'C'.repeat(20)}0001`
  const cis2 = `01${gtin}21${'D'.repeat(20)}0002`
  const poolRes = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([{ title: 'E2E Catalog Pool', product_ids: [productId] }]),
      files: {
        name: 'codes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(`cis\n${cis1}\n${cis2}`),
      },
    },
  })
  expect(poolRes.ok()).toBeTruthy()

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  const row = page.getByTestId('ff-product-row').filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(page.getByTestId(`ff-honest-sign-status-${productId}`)).toHaveText('ЧЗ')
  const markingLink = page.getByTestId(`ff-catalog-marking-link-${productId}`)
  await expect(markingLink).toBeVisible()
  await expect(markingLink).toContainText('2')
  await markingLink.click()
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/product/${productId}`))
  await expect(page.getByTestId('ff-honest-sign-product-page')).toBeVisible()
})

// TC-CAT-04 — FF создаёт один товар вручную как вспомогательный путь каталога.
// Given: FF admin и селлер; When: «Создать товар»; Then: товар появляется в каталоге без отдельного chip происхождения.
test('ff products: manual create adds a catalog product', async ({ page }) => {
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
  const createdRow = page.getByTestId('ff-product-row').filter({ hasText: sku })
  await expect(createdRow).toContainText(barcode)
  await expect(createdRow.getByText('Вручную', { exact: true })).toHaveCount(0)
  void seller
})

// TC-CAT-04 — массовый путь каталога: скачать шаблон → загрузить Excel → preview → apply.
// TC-NEW-MAN-02 — FF загружает Excel ТЗ: preview → apply → товары с ТЗ.
// TC-NEW-PRODUCT-TZ-02 — повтор файла защищён backend-идемпотентностью (API regression test).
// TC-NEW-TZ-STOCK-002 — во время apply нельзя сменить селлера/файл или закрыть диалог через Cancel/ESC.
// Given: FF admin, селлер, xlsx с названием, артикулом, SKU, ШК, WB/nmId, размером и объединённым ТЗ;
// When: «Загрузить Excel» и Применить;
// Then: импорт находит нужный лист по структуре колонок (имя листа не важно), товары в каталоге,
// ТЗ заполнено.
test('ff products: import tz xlsx creates catalog products with packaging', async ({ page }) => {
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
ws.append(["Название товара","Артикул продавца","SKU","Штрихкод","WB/nmId","Размер","ТЗ упаковки"])
ws.append(["E2E Clean Title","E2E-ART","E2E-ART-46","2039000000001",123456789,46,None])
ws.append(["E2E Clean Title","E2E-ART","E2E-ART-48","2039000000002",123456789,48,None])
ws["G2"] = "E2E merged TZ"
ws.merge_cells("G2:G3")
wb.save(${JSON.stringify(xlsxPath)})
bad = Workbook()
bad_ws = bad.active
bad_ws.title = "Ошибочный дубль"
bad_ws.append(["Название товара","Артикул продавца","SKU","Штрихкод","WB/nmId","Размер","ТЗ упаковки"])
bad_ws.append(["E2E Bad Title","E2E-BAD","E2E-BAD-46","2039000000099",123456780,46,"TZ"])
bad_ws.append(["E2E Bad Title 2","E2E-BAD","E2E-BAD-48","2039000000099",123456780,48,"TZ"])
bad.save(${JSON.stringify(badXlsxPath)})
`
  execFileSync('python3', ['-c', py], { stdio: 'pipe' })

  await page.reload()
  await page.getByTestId('nav-ff-products').click()
  await expect(page.getByTestId('ff-products-list')).toBeVisible()
  await page.getByTestId('ff-products-import-tz').click()
  await expect(page.getByTestId('ff-tz-import-dialog')).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('ff-tz-import-template').click()
  const templateDownload = await downloadPromise
  expect(templateDownload.suggestedFilename()).toContain('wms-product-catalog-template')
  await page.getByTestId('ff-tz-import-seller').click()
  await page.getByRole('listbox').getByText('TZ Seller', { exact: true }).click()

  await page.getByTestId('ff-tz-import-file').locator('input[type="file"]').setInputFiles(xlsxPath)
  await expect(page.getByTestId('ff-tz-import-summary')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('ff-tz-import-summary')).toContainText('создать 2')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('E2E Clean Title')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('E2E-ART')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('E2E-ART-46')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('123456789')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText('создать')

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
    'Создано: 2, обновлено: 0, пропущено: 0',
  )
  await expect(page.getByTestId('ff-products-table')).toContainText('E2E Clean Title')
  await expect(page.getByTestId('ff-products-table')).toContainText('E2E-ART')
  await expect(page.getByTestId('ff-product-row')).toHaveCount(2)
  await expect(page.getByTestId('ff-products-table')).toContainText('2039000000001')
  const importedRow = page.getByTestId('ff-product-row').filter({ hasText: 'E2E-ART-46' })
  await importedRow.getByRole('button', { name: 'Редактировать ТЗ' }).click()
  await expect(page.getByTestId('ff-packaging-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-packaging-text')).toHaveValue('E2E merged TZ')
  await page.getByTestId('ff-packaging-dialog').getByRole('button', { name: 'Отмена' }).click()

  await page.getByTestId('ff-products-import-tz').click()
  await page.getByTestId('ff-tz-import-seller').click()
  await page.getByRole('listbox').getByText('TZ Seller', { exact: true }).click()
  await page
    .getByTestId('ff-tz-import-file')
    .locator('input[type="file"]')
    .setInputFiles(badXlsxPath)
  await expect(page.getByTestId('ff-tz-import-summary')).toContainText('ошибок 1')
  await expect(page.getByTestId('ff-tz-import-preview-table')).toContainText(
    'Дубликат штрихкода в файле',
  )
  await expect(page.getByTestId('ff-tz-import-apply')).toBeDisabled()
})
