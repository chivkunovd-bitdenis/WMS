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

  const row = page.getByTestId(`ff-reports-row-${seed.productId}`)
  await expect(row).toBeVisible({ timeout: 15_000 })
  await expect(row).toContainText('Box Product')
  await expect(row).toContainText(seed.sku)
  // Группа «Приёмка» человеко-понятная, техническое имя inbound_intake на экране не встречается.
  await expect(page.getByTestId('ff-reports-table')).toContainText('Приёмка')
  await expect(page.getByTestId('ff-reports-table')).not.toContainText('inbound_intake')
  // Приход по приёмке и итоговое нетто равны заведённому количеству — движения полные.
  const cells = row.locator('td')
  await expect(cells.nth(5)).toHaveText('6') // Приёмка, приход
  await expect(cells.last()).toHaveText('6') // Итого, нетто

  // Поиск по товару сужает список до одной строки.
  await page.getByTestId('ff-reports-search').fill('Box Product')
  await expect(page.getByTestId(`ff-reports-row-${seed.productId}`)).toBeVisible()
  await page.getByTestId('ff-reports-search').fill('нет-такого-товара-xyz')
  await expect(page.getByTestId('ff-reports-table')).toContainText('движений не найдено')
})
