import { expect, test } from '@playwright/test'

import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  seedFfSellerInbound,
  INBOUND_API,
} from './inbound-boxes-helpers'

// S-33-TC-003 / S-33-TC-014 — a technical FBS warehouse must not turn a
// single physical warehouse into a visible report scope selector.
test('FF reports exclude service warehouses from the warehouse filter', async ({ page }) => {
  await seedFfSellerInbound(page, `ff-reports-warehouse-${Date.now()}`)
  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    const response = await route.fetch()
    const rows = (await response.json()) as { id: string; name: string; code: string }[]
    await route.fulfill({
      response,
      contentType: 'application/json',
      body: JSON.stringify([
        ...rows,
        { id: 'service-fbs-archive', name: 'FBS WB Архив', code: 'fbs-wb-archive' },
      ]),
    })
  })

  await page.reload()
  await page.getByTestId('nav-ff-reports').click()

  await expect(page).toHaveURL('/app/ff/reports')
  await expect(page.getByTestId('ff-reports-page')).toBeVisible()
  await expect(page.getByTestId('ff-reports-warehouse')).toHaveCount(0)
})

// Раздел «Отчёты» у ФФ: сводка приход/расход по товару за период (журнал inventory_movements).
// Проверяем, что раздел открывается, таблица рисуется с реальными данными по товару и
// что поиск по товару фильтрует строки — а не только что страница не падает.
test('FF reports: section opens and shows movement summary for a product with intake', async ({
  page,
}) => {
  test.setTimeout(90_000)
  const seed = await seedFfSellerInbound(page)
  const adminHeaders = { Authorization: `Bearer ${seed.token}` }

  const rid = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 1,
    expectedQty: 6,
  })
  const { boxes } = await beginInboundReceivingWithBoxes(page.request, adminHeaders, rid, {
    boxCount: 1,
  })
  await fulfillInboundViaBoxScans(page.request, adminHeaders, rid, boxes, seed.sku, [6])
  const verify = await page.request.post(`${INBOUND_API}/${rid}/verify`, {
    headers: adminHeaders,
  })
  expect(verify.ok()).toBeTruthy()
  const post = await page.request.post(`${INBOUND_API}/${rid}/post`, { headers: adminHeaders })
  expect(post.ok()).toBeTruthy()

  await page.getByTestId('nav-ff-reports').click()
  await expect(page.getByTestId('ff-reports-page')).toBeVisible()
  await expect(page.getByTestId('ff-reports-table')).toBeVisible()

  // TC-NEW-F07-010 — dates appear only for the explicit custom-period choice.
  await expect(page.getByTestId('ff-reports-date-from')).toHaveCount(0)
  await page.getByTestId('ff-reports-period').click()
  await page.getByRole('option', { name: 'Другой период' }).click()
  await expect(page.getByTestId('ff-reports-date-from').locator('input')).not.toHaveValue('')
  await expect(page.getByTestId('ff-reports-date-to').locator('input')).not.toHaveValue('')

  const row = page.getByTestId('ff-reports-table').locator('tbody tr').first()
  await expect(row).toBeVisible({ timeout: 15_000 })
  await expect(row).toContainText('Box Product')
  await expect(row).toContainText(seed.sku)
  // Товарная группировка показывает фиксированные товарные колонки и агрегаты.
  await expect(page.getByTestId('ff-reports-table')).toContainText('Остаток сейчас')
  await expect(page.getByTestId('ff-reports-table')).toContainText('Приход')
  await expect(page.getByTestId('ff-reports-table')).not.toContainText('inbound_intake')
  await expect(row.locator('td').last()).toHaveText('6')

  // Поиск по товару сужает список до одной строки.
  await page.getByTestId('filter-search').fill('Box Product')
  await expect(page.getByTestId('ff-reports-table').locator('tbody tr').first()).toBeVisible()
  await page.getByTestId('filter-search').fill('нет-такого-товара-xyz')
  await expect(page.getByTestId('ff-reports-table')).toContainText('За выбранный период движений нет')

  // TC-NEW-F07-011 — grouping changes only the server table query; the summary stays visible.
  await expect(page.getByTestId('ff-reports-download-csv')).toBeDisabled()
  await page.getByTestId('ff-reports-download-csv').hover()
  await expect(page.getByText('За выбранный период нечего выгружать')).toBeVisible()
  await page.getByTestId('filter-search').fill('Box Product')
  await expect(page.getByTestId('ff-reports-table').locator('tbody tr').first()).toBeVisible()
  const metrics = await page.getByTestId('ff-reports-metrics').innerText()

  // The server owns the page slice. This response fixture gives the screen a
  // 51-row result, so the browser path can exercise page two without relying
  // on an implementation detail of the reporting database seed.
  await page.route('**/api/reports/inventory?**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const pageNumber = Number(requestUrl.searchParams.get('page') ?? '1')
    const grouping = requestUrl.searchParams.get('group_by') ?? 'product'
    if (grouping === 'operation') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          group_by: 'operation', page: pageNumber, page_size: 50, total: 1,
          rows: [{ operation: 'Приёмка', in_qty: 6, out_qty: 0, net: 6 }],
        }),
      })
      return
    }
    const rows = Array.from({ length: pageNumber === 2 ? 1 : 50 }, (_, index) => {
      const number = pageNumber === 2 ? 50 : index
      return {
        product_id: `report-product-${number}`,
        sku_code: `REPORT-SKU-${String(number).padStart(3, '0')}`,
        product_name: `Report product ${number}`,
        photo_url: null,
        wb_vendor_code: null,
        wb_barcode: null,
        seller_name: 'Box Seller',
        current_balance: 1,
        total_in: 1,
        total_out: 0,
        net: 1,
      }
    })
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ group_by: 'product', page: pageNumber, page_size: 50, total: 51, rows }),
    })
  })

  await page.getByTestId('ff-reports-grouping').click()
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/reports/inventory?') && new URL(response.url()).searchParams.get('group_by') === 'operation'),
    page.getByRole('option', { name: 'По операциям' }).click(),
  ])
  await expect(page.getByTestId('ff-reports-table')).toContainText('Операция')
  await expect(page.getByTestId('ff-reports-metrics')).toHaveText(metrics)
  await page.getByTestId('ff-reports-grouping').click()
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/reports/inventory?') && new URL(response.url()).searchParams.get('group_by') === 'product'),
    page.getByRole('option', { name: 'По товарам' }).click(),
  ])
  await expect(page.getByTestId('ff-reports-pagination')).toContainText('1–50 из 51')
  await expect(page.getByTestId('ff-reports-next-page')).toBeEnabled()
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/reports/inventory?') && new URL(response.url()).searchParams.get('page') === '2'),
    page.getByTestId('ff-reports-next-page').click(),
  ])
  await expect(page.getByTestId('ff-reports-pagination')).toContainText('51–51 из 51')
  await expect(page.getByTestId('ff-reports-table')).toContainText('REPORT-SKU-050')
  await expect(page.getByTestId('ff-reports-metrics')).toHaveText(metrics)

  // TC-NEW-F07-012 — export is a server CSV, not an HTML/XLS download.
  await page.route('**/api/reports/inventory/export.csv?**', async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'content-disposition': 'attachment; filename="inventory-report.csv"',
        'content-type': 'text/csv; charset=utf-8',
      },
      body: 'Товар,Название\nREPORT-SKU-050,Report product 50\n',
    })
  })
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.waitForResponse((response) => response.url().includes('/api/reports/inventory/export.csv') && response.headers()['content-type'].startsWith('text/csv')),
    page.getByTestId('ff-reports-download-csv').click(),
  ])
  expect(download.suggestedFilename()).toBe('inventory-report.csv')
  expect(await download.createReadStream()).not.toBeNull()
})
