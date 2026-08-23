import { expect, test } from '@playwright/test'

import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  seedFfSellerInbound,
  INBOUND_API,
} from './inbound-boxes-helpers'

const overviewFixture = (overrides: Record<string, unknown> = {}) => ({
  current_balance: 12,
  in_qty: 7,
  out_qty: 4,
  comparison: { previous_out_qty: 2, change_percent: 100, change: 2 },
  daily: [
    { date: '2026-08-01', in_qty: 7, out_qty: 1, previous_out_qty: 2 },
    { date: '2026-08-02', in_qty: 0, out_qty: 3, previous_out_qty: 0 },
  ],
  generated_at: '2026-08-23T05:00:00+00:00',
  source_freshness: null,
  warnings: [],
  ...overrides,
})

const productReportFixture = (name = 'Report product') => ({
  group_by: 'product', page: 1, page_size: 50, total: 1,
  rows: [{
    product_id: 'report-product', sku_code: 'REPORT-SKU', product_name: name,
    photo_url: null, wb_vendor_code: null, wb_barcode: null, seller_name: 'Box Seller',
    current_balance: 12, total_in: 7, total_out: 4, net: 3, integrity_error: false,
  }],
})

// S-33-TC-015 — Given an FF staff member with cells access but without inventory
// access, When they open the report route directly, Then the visible access-denied
// state replaces the report and no reporting data is requested.
test('FF staff with cells access but without inventory access cannot open the direct reports route', async ({ page }) => {
  const suffix = `ff-reports-denied-${Date.now()}`
  const seed = await seedFfSellerInbound(page, suffix)
  const staffEmail = `${suffix}@example.com`
  const staffPassword = 'password123'
  const adminHeaders = { Authorization: `Bearer ${seed.token}` }

  const created = await page.request.post('/api/auth/staff-accounts', {
    headers: adminHeaders,
    data: { email: staffEmail },
  })
  expect(created.status()).toBe(201)
  const staffId = String(((await created.json()) as { id: string }).id)
  const permissions = await page.request.patch(`/api/auth/staff-accounts/${staffId}/permissions`, {
    headers: adminHeaders,
    data: {
      settings: false,
      mp_shipments: false,
      reception: true,
      cells: true,
      inventory: false,
      packaging: false,
      shift_lead: false,
    },
  })
  expect(permissions.status()).toBe(200)
  const passwordSetup = await page.request.post('/api/auth/set-initial-password', {
    data: { email: staffEmail, password: staffPassword },
  })
  expect(passwordSetup.status()).toBe(200)

  await page.getByTestId('logout').click()
  const loginForm = page.getByTestId('login-form')
  await expect(loginForm).toBeVisible()
  await loginForm.getByLabel('Email').fill(staffEmail)
  await loginForm.getByLabel('Пароль').fill(staffPassword)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/auth/login') && response.ok()),
    page.waitForResponse((response) => response.url().includes('/api/auth/me') && response.ok()),
    loginForm.getByRole('button', { name: 'Войти' }).click(),
  ])

  let reportRequests = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/reports/')) reportRequests += 1
  })
  await page.goto('/app/ff/reports')

  await expect(page).toHaveURL('/app/ff/reports')
  await expect(page.getByTestId('ff-access-denied')).toContainText('Нет доступа к этому разделу.')
  await expect(page.getByTestId('nav-ff-reports')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-page')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-metrics')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-chart')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-table')).toHaveCount(0)
  expect(reportRequests).toBe(0)
})

// S-33-TC-008 — a late page response cannot overwrite a freshly filtered
// slice, and a table failure is not presented as a valid empty report.
test('FF report keeps one table slice and distinguishes a table error from empty data', async ({ page }) => {
  await seedFfSellerInbound(page, `ff-report-table-state-${Date.now()}`)

  let releaseOldPage: (() => void) | undefined
  let markOldPageStarted: (() => void) | undefined
  let markOldPageHandled: (() => void) | undefined
  const oldPageRelease = new Promise<void>((resolve) => { releaseOldPage = resolve })
  const oldPageStarted = new Promise<void>((resolve) => { markOldPageStarted = resolve })
  const oldPageHandled = new Promise<void>((resolve) => { markOldPageHandled = resolve })

  await page.route('**/api/reports/overview?**', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture()) })
  })
  await page.route('**/api/reports/inventory?**', async (route) => {
    const url = new URL(route.request().url())
    const search = url.searchParams.get('search') ?? ''
    if (url.searchParams.get('page') === '2') {
      markOldPageStarted?.()
      await oldPageRelease
      try {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
          ...productReportFixture('Stale page result'), page: 2,
        }) })
      } catch {
        // The screen is expected to abort this request when the filter changes.
      } finally {
        markOldPageHandled?.()
      }
      return
    }
    if (search === 'table-error') {
      await route.fulfill({ status: 503, body: 'table unavailable' })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      ...productReportFixture(search === 'fresh-slice' ? 'Fresh filtered result' : undefined),
      total: 51,
    }) })
  })

  await page.getByTestId('nav-ff-reports').click()
  await expect(page.getByTestId('ff-reports-table')).toContainText('Report product')
  await expect(page.getByRole('columnheader', { name: 'Остаток сейчас' })).toHaveAttribute('width', '130')
  await expect(page.getByRole('columnheader', { name: 'Приход' })).toHaveAttribute('width', '110')
  await expect(page.getByRole('columnheader', { name: 'Расход' })).toHaveAttribute('width', '110')
  await expect(page.getByRole('columnheader', { name: 'Нетто' })).toHaveAttribute('width', '100')

  await page.getByTestId('ff-reports-next-page').click()
  await oldPageStarted
  await page.getByTestId('filter-search').fill('fresh-slice')
  await expect(page.getByTestId('ff-reports-table')).toContainText('Fresh filtered result')
  await expect(page.getByTestId('ff-reports-table').locator('tbody .MuiSkeleton-root')).toHaveCount(0)
  releaseOldPage?.()
  await oldPageHandled
  await page.waitForTimeout(100)
  await expect(page.getByTestId('ff-reports-table')).toContainText('Fresh filtered result')
  await expect(page.getByTestId('ff-reports-table')).not.toContainText('Stale page result')

  await page.getByTestId('filter-search').fill('table-error')
  await expect(page.getByTestId('ff-reports-table-error')).toBeVisible()
  await expect(page.getByTestId('ff-reports-table')).toHaveCount(0)
  await expect(page.getByText('За выбранный период движений нет')).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-download-csv')).toBeDisabled()
  await page.getByTestId('ff-reports-download-csv').hover()
  await expect(page.getByText('Строки отчёта не загружены')).toBeVisible()
})

// S-33-TC-003 / S-33-TC-014 — only the API operational flag defines which
// warehouses belong to the report, even after a service warehouse is renamed.
test('FF reports exclude non-operational warehouses from the warehouse filter', async ({ page }) => {
  await seedFfSellerInbound(page, `ff-reports-warehouse-${Date.now()}`)
  await page.route('**/api/warehouses', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    const response = await route.fetch()
    const rows = (await response.json()) as {
      id: string
      name: string
      code: string
      is_operational: boolean
    }[]
    const operationalWarehouse = rows.find((warehouse) => warehouse.is_operational)
    if (!operationalWarehouse) throw new Error('Expected an operational warehouse fixture')
    await route.fulfill({
      response,
      contentType: 'application/json',
      body: JSON.stringify([
        operationalWarehouse,
        {
          id: 'service-fbs-archive',
          name: 'Архив',
          code: 'fbs-wb-archive',
          is_operational: false,
        },
      ]),
    })
  })

  await page.reload()
  await page.getByTestId('nav-ff-reports').click()

  await expect(page).toHaveURL('/app/ff/reports')
  await expect(page.getByTestId('ff-reports-page')).toBeVisible()
  await expect(page.getByRole('option', { name: 'Архив' })).toHaveCount(0)
  await expect(page.getByTestId('ff-reports-warehouse')).toHaveCount(0)
})

// S-33-TC-003 / S-33-TC-007 / S-33-TC-012 / S-33-TC-013 / S-33-TC-014 —
// filters replace the whole slice with skeletons, warnings are rendered from
// the API envelope, and an overview retry preserves the usable table.
test('FF report upper slice updates atomically and keeps table on overview retry', async ({ page }) => {
  await seedFfSellerInbound(page, `ff-report-slice-${Date.now()}`)

  let holdRequests = false
  let releaseRequests: (() => void) | undefined
  let held = Promise.resolve()
  let overviewAttemptsAfterError = 0
  let inventoryCalls = 0
  let releaseSlowTable: (() => void) | undefined
  const slowTable = new Promise<void>((resolve) => { releaseSlowTable = resolve })
  const requestedOverviewUrls: URL[] = []

  await page.route('**/api/reports/overview?**', async (route) => {
    const url = new URL(route.request().url())
    requestedOverviewUrls.push(url)
    if (holdRequests) await held
    const search = url.searchParams.get('search') ?? ''
    if (search === 'summary-error') {
      overviewAttemptsAfterError += 1
      if (overviewAttemptsAfterError === 1) {
        await route.fulfill({ status: 503, body: 'summary unavailable' })
        return
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture()) })
      return
    }
    if (search === 'empty') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture({
        current_balance: 9, in_qty: 0, out_qty: 0,
        comparison: { previous_out_qty: 0, change_percent: null, change: 0 }, daily: [],
      })) })
      return
    }
    if (search === 'no-base') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture({
        comparison: { previous_out_qty: 0, change_percent: null, change: 4 },
      })) })
      return
    }
    if (search === 'stale') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture({
        warnings: [
          { code: 'wildberries_stale', source: 'wildberries', last_updated_at: '2026-08-22T16:12:00+00:00' },
          { code: 'reporting_dimensions_legacy', count: 3 },
        ],
      })) })
      return
    }
    const isSevenDays = url.searchParams.get('date_from') !== '2026-08-01T00:00:00+03:00'
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture(isSevenDays ? {
      current_balance: 70,
      in_qty: 14,
      out_qty: 8,
      daily: [
        { date: '2026-08-17', in_qty: 1, out_qty: 7, previous_out_qty: 0 },
        { date: '2026-08-23', in_qty: 13, out_qty: 1, previous_out_qty: 2 },
      ],
    } : {})) })
  })

  await page.route('**/api/reports/inventory?**', async (route) => {
    inventoryCalls += 1
    if (holdRequests) await held
    const url = new URL(route.request().url())
    if (url.searchParams.get('group_by') === 'operation') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        group_by: 'operation', page: 1, page_size: 50, total: 1,
        rows: [{ operation: 'Перемещение: ушло', in_qty: 0, out_qty: 3, net: -3, integrity_error: true }],
      }) })
      return
    }
    const search = url.searchParams.get('search') ?? ''
    if (search === 'summary-error') await slowTable
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(
      search === 'empty' || search === 'no-base' || search === 'stale'
        ? { group_by: 'product', page: 1, page_size: 50, total: 0, rows: [] }
        : productReportFixture(search === 'summary-error' ? 'Table remains available' : undefined),
    ) })
  })

  await page.getByTestId('nav-ff-reports').click()
  await expect(page.getByTestId('ff-reports-metrics-balance')).toContainText('12')
  const initialOutboundPoints = await page.getByTestId('ff-reports-chart').locator('polyline').nth(1).getAttribute('points')

  holdRequests = true
  held = new Promise<void>((resolve) => { releaseRequests = resolve })
  await page.getByTestId('ff-reports-period').click()
  await page.getByRole('option', { name: '7 дней' }).click()
  await expect(page.getByTestId('ff-reports-metrics-balance-skeleton')).toBeVisible()
  await expect(page.getByTestId('ff-reports-chart-skeleton')).toBeVisible()
  await expect(page.getByTestId('ff-reports-table').locator('tbody .MuiSkeleton-root').first()).toBeVisible()
  releaseRequests?.()
  holdRequests = false
  await expect(page.getByTestId('ff-reports-metrics-balance')).toContainText('70')
  await expect.poll(async () => page.getByTestId('ff-reports-chart').locator('polyline').nth(1).getAttribute('points')).not.toBe(initialOutboundPoints)
  const sevenDayRequest = requestedOverviewUrls.at(-1)
  expect(sevenDayRequest?.searchParams.get('date_from')).toMatch(/T00:00:00\+03:00$/)
  expect(sevenDayRequest?.searchParams.get('date_to')).toMatch(/T00:00:00\+03:00$/)

  await page.getByTestId('filter-search').fill('empty')
  await expect(page.getByTestId('ff-reports-metrics-balance')).toContainText('9')
  await expect(page.getByTestId('ff-reports-chart')).toContainText('За выбранный период движений нет')

  await page.getByTestId('filter-search').fill('no-base')
  await expect(page.getByTestId('ff-reports-metrics-comparison')).toContainText('—')
  await expect(page.getByTestId('ff-reports-metrics-comparison')).toContainText('В прошлом периоде расхода не было')

  await page.getByTestId('filter-search').fill('stale')
  await expect(page.getByTestId('ff-reports-warning')).toHaveCount(2)
  await expect(page.getByTestId('ff-reports-warning').first()).toContainText('Данные Wildberries могут быть неполными')
  await expect(page.getByTestId('ff-reports-warning').nth(1)).toContainText('3 исторических записей')

  await page.getByTestId('filter-search').fill('summary-error')
  await expect(page.getByTestId('ff-reports-summary-error')).toBeVisible()
  await expect(page.getByTestId('ff-reports-table').locator('tbody .MuiSkeleton-root').first()).toBeVisible()
  const callsBeforeRetry = inventoryCalls
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/reports/overview?') && response.status() === 200),
    page.getByTestId('ff-reports-summary-error').getByRole('button', { name: 'Повторить' }).click(),
  ])
  releaseSlowTable?.()
  await expect(page.getByTestId('ff-reports-metrics-balance')).toContainText('12')
  await expect(page.getByTestId('ff-reports-table')).toContainText('Table remains available')
  expect(inventoryCalls).toBe(callsBeforeRetry)

  await page.getByTestId('ff-reports-grouping').click()
  await page.getByRole('option', { name: 'По операциям' }).click()
  await expect(page.getByTestId('ff-reports-integrity-error')).toContainText('отчёт ничего не достраивал')
  const problemRow = page.getByTestId('ff-reports-table').locator('tbody tr').first()
  await expect(problemRow).toContainText('Перемещение: ушло')
  await expect(problemRow.getByTestId('ff-reports-row-integrity-error')).toHaveText('Ошибка')
  await expect(problemRow.locator('td').nth(1)).toHaveText('—')
  await expect(problemRow.locator('td').nth(2)).toHaveText('3')
})

// S-33-TC-001 — December's current-month preset ends at the exclusive first
// day of the next year instead of producing a reversed interval.
test('FF report current month crosses the December year boundary', async ({ page }) => {
  await seedFfSellerInbound(page, `ff-report-december-${Date.now()}`)
  await page.clock.setFixedTime(new Date('2026-12-15T09:00:00+03:00'))
  let requestedUrl: URL | undefined
  await page.route('**/api/reports/overview?**', async (route) => {
    requestedUrl = new URL(route.request().url())
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(overviewFixture()) })
  })
  await page.route('**/api/reports/inventory?**', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(productReportFixture()) })
  })

  await page.getByTestId('nav-ff-reports').click()
  await expect(page.getByTestId('ff-reports-metrics')).toBeVisible()
  expect(requestedUrl?.searchParams.get('date_from')).toBe('2026-12-01T00:00:00+03:00')
  expect(requestedUrl?.searchParams.get('date_to')).toBe('2027-01-01T00:00:00+03:00')
  await expect(page.getByTestId('ff-reports-period-error')).toHaveCount(0)
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
  // TC-NEW-F07-013 — Given a report with more than 50 rows, When the operator
  // opens the first page, Then pagination is one equal-size navigation group:
  // «Назад» explains that it is unavailable, while «Вперёд» opens page two
  // without changing the upper aggregates.
  const previousPage = page.getByTestId('ff-reports-previous-page')
  const nextPage = page.getByTestId('ff-reports-next-page')
  await expect(previousPage).toBeDisabled()
  await expect(nextPage).toBeEnabled()
  const previousBounds = await previousPage.boundingBox()
  const nextBounds = await nextPage.boundingBox()
  expect(previousBounds).not.toBeNull()
  expect(nextBounds).not.toBeNull()
  expect(previousBounds?.width).toBe(nextBounds?.width)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/reports/inventory?') && new URL(response.url()).searchParams.get('page') === '2'),
    nextPage.click(),
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
