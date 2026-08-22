import { expect, test } from '@playwright/test'

import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  seedFfSellerInbound,
  INBOUND_API,
} from './inbound-boxes-helpers'

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

  // Период по умолчанию — текущий месяц (оба поля заполнены датами, не пустые).
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
  await page.getByTestId('ff-reports-search').fill('Box Product')
  await expect(page.getByTestId('ff-reports-table').locator('tbody tr').first()).toBeVisible()
  await page.getByTestId('ff-reports-search').fill('нет-такого-товара-xyz')
  await expect(page.getByTestId('ff-reports-table')).toContainText('движений не найдено')

  // TC-NEW-F07-011 — grouping changes only the server table query; the summary stays visible.
  await expect(page.getByTestId('ff-reports-download-csv')).toBeDisabled()
  await page.getByTestId('ff-reports-download-csv').hover()
  await expect(page.getByText('За выбранный период нечего выгружать')).toBeVisible()
  await page.getByTestId('ff-reports-search').fill('Box Product')
  const metrics = await page.getByTestId('ff-reports-metrics').innerText()
  await page.getByTestId('ff-reports-grouping').click()
  await page.getByRole('option', { name: 'По операциям' }).click()
  await expect(page.getByTestId('ff-reports-table')).toContainText('Операция')
  await expect(page.getByTestId('ff-reports-metrics')).toHaveText(metrics)
  await page.getByTestId('ff-reports-grouping').click()
  await page.getByRole('option', { name: 'По товарам' }).click()

  // TC-NEW-F07-013 — pagination changes only the table request and keeps the metrics visible.
  await expect(page.getByTestId('ff-reports-next-page')).toBeEnabled()
  await page.getByTestId('ff-reports-next-page').click()
  await expect(page.getByTestId('ff-reports-pagination')).toContainText('51–')
  await expect(page.getByTestId('ff-reports-metrics')).toHaveText(metrics)

  // TC-NEW-F07-012 — export is a server CSV, not an HTML/XLS download.
  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('ff-reports-download-csv').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('inventory-report.csv')
  expect(await download.createReadStream()).not.toBeNull()
})
