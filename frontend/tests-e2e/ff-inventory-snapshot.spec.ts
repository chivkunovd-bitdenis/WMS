import { expect, test } from '@playwright/test'

import { waitForGetOk, waitForPostOk } from './api-waits'
import {
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  seedFfSellerInbound,
} from './inbound-boxes-helpers'

const MSK_TIME_ZONE = 'Europe/Moscow'

function currentMskMonthValue(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MSK_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(new Date())
  const year = parts.find((p) => p.type === 'year')?.value ?? '1970'
  const month = parts.find((p) => p.type === 'month')?.value ?? '01'
  return `${year}-${month}`
}

function previousMonthValue(monthValue: string): string {
  const [yearRaw, monthRaw] = monthValue.split('-').map(Number)
  const year = yearRaw || 1970
  const month = monthRaw || 1
  if (month === 1) {
    return `${year - 1}-12`
  }
  return `${year}-${String(month - 1).padStart(2, '0')}`
}

// TC-NEW-F12-001 — FF inventory: monthly stock snapshot screen, historical empty state,
// current-month run/read-back, visible product identity and four stock numbers.
// Given: FF admin has a stocked seller product with FBS and reserve directions; When: opens
// /app/ff/inventory, selects historical/current month and runs snapshot; Then: historical month
// has no run action, current month stores and reads back the first slice; negative: no product_id,
// raw backend codes, formulas, charts, or placeholder text are visible.
test('ff inventory snapshot: historical empty and current run/read-back', async ({ page }) => {
  test.setTimeout(120_000)
  const suffix = String(Date.now())
  const seed = await seedFfSellerInbound(page, suffix)
  const auth = { Authorization: `Bearer ${seed.token}` }

  const locRes = await page.request.post(`/api/warehouses/${seed.warehouseId}/locations`, {
    headers: auth,
    data: { code: `SNAP-${suffix.slice(-5)}` },
  })
  expect(locRes.ok()).toBeTruthy()
  const locationId = String(((await locRes.json()) as { id: string }).id)

  const baseIn = '/api/operations/inbound-intake-requests'
  const inbound = await page.request.post(baseIn, {
    headers: auth,
    data: { warehouse_id: seed.warehouseId },
  })
  expect(inbound.ok()).toBeTruthy()
  const inboundId = String(((await inbound.json()) as { id: string }).id)
  const line = await page.request.post(`${baseIn}/${inboundId}/lines`, {
    headers: auth,
    data: {
      product_id: seed.productId,
      expected_qty: 10,
      storage_location_id: locationId,
    },
  })
  expect(line.ok()).toBeTruthy()
  const submit = await page.request.post(`${baseIn}/${inboundId}/submit`, { headers: auth })
  expect(submit.ok()).toBeTruthy()
  const { boxes } = await beginInboundReceivingWithBoxes(page.request, auth, inboundId, {
    boxCount: 1,
  })
  await fulfillInboundViaBoxScans(page.request, auth, inboundId, boxes, seed.sku, [10])
  const verify = await page.request.post(`${baseIn}/${inboundId}/verify`, { headers: auth })
  expect(verify.ok()).toBeTruthy()
  const post = await page.request.post(`${baseIn}/${inboundId}/post`, { headers: auth })
  expect(post.ok()).toBeTruthy()

  const fbs = await page.request.post(`/api/products/${seed.productId}/stock-directions`, {
    headers: auth,
    data: { name: 'FBS-пул', quantity: 3, is_fbs: true },
  })
  expect(fbs.ok()).toBeTruthy()
  const reserve = await page.request.post(`/api/products/${seed.productId}/stock-directions`, {
    headers: auth,
    data: { name: 'Резерв отгрузки', quantity: 2, is_fbs: false },
  })
  expect(reserve.ok()).toBeTruthy()

  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-balances/monthly-snapshots'),
    page.getByTestId('nav-ff-inventory').click(),
  ])
  await expect(page.getByTestId('ff-inventory-snapshot-screen')).toBeVisible()
  await expect(page.getByTestId('ff-inventory-placeholder')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Снимки остатков' })).toBeVisible()
  await expect(page.getByTestId('ff-inventory-snapshot-empty')).toContainText(
    'Снимок еще не сформирован',
  )

  const currentMonth = currentMskMonthValue()
  const historicalMonth = previousMonthValue(currentMonth)
  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-balances/monthly-snapshots'),
    page.getByTestId('ff-inventory-snapshot-month').fill(historicalMonth),
  ])
  await expect(page.getByTestId('ff-inventory-snapshot-empty')).toContainText(
    'За этот месяц снимка нет',
  )
  await expect(page.getByTestId('ff-inventory-snapshot-run')).toBeDisabled()

  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-balances/monthly-snapshots'),
    page.getByTestId('ff-inventory-snapshot-month').fill(currentMonth),
  ])
  await expect(page.getByTestId('ff-inventory-snapshot-run')).toBeEnabled()
  await Promise.all([
    waitForPostOk(page, '/api/operations/inventory-balances/monthly-snapshots/run'),
    page.getByTestId('ff-inventory-snapshot-run').click(),
  ])

  const row = page.getByTestId('ff-inventory-snapshot-row').first()
  await expect(row).toContainText('Box Product')
  await expect(row).toContainText(seed.sku)
  await expect(page.getByTestId('ff-inventory-snapshot-total-0')).toHaveText('10')
  await expect(page.getByTestId('ff-inventory-snapshot-fbs-0')).toHaveText('3')
  await expect(page.getByTestId('ff-inventory-snapshot-reserved-0')).toHaveText('2')
  await expect(page.getByTestId('ff-inventory-snapshot-free-fbo-0')).toHaveText('5')
  await expect(page.getByTestId('ff-inventory-snapshot-run')).toBeDisabled()

  await Promise.all([
    waitForGetOk(page, '/api/operations/inventory-balances/monthly-snapshots'),
    page.reload(),
  ])
  await expect(page.getByTestId('ff-inventory-snapshot-table')).toBeVisible()
  await expect(page.getByTestId('ff-inventory-snapshot-total-0')).toHaveText('10')
  await expect(page.getByTestId('ff-inventory-snapshot-fbs-0')).toHaveText('3')
  await expect(page.getByTestId('ff-inventory-snapshot-reserved-0')).toHaveText('2')
  await expect(page.getByTestId('ff-inventory-snapshot-free-fbo-0')).toHaveText('5')

  const visibleText = await page.getByTestId('ff-inventory-snapshot-screen').innerText()
  expect(visibleText).not.toContain(seed.productId)
  expect(visibleText).not.toContain('product_id')
  expect(visibleText).not.toContain('monthly_snapshot')
  expect(visibleText).not.toContain('Раздел в разработке')
  expect(visibleText).not.toContain('Формула')
  expect(visibleText).not.toContain('UUID')
})
