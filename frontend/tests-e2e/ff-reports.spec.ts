import { expect, test } from '@playwright/test'

import {
  apiCreateSubmittedInbound,
  beginInboundReceivingWithBoxes,
  fulfillInboundViaBoxScans,
  seedFfSellerInbound,
  INBOUND_API,
} from './inbound-boxes-helpers'

// Раздел «Отчёты» у ФФ: сводка приход/расход по товару за период (журнал inventory_movements).
// TC-NEW-WMS703-E7 — отчёт показывает приёмку и не дублирует приход при повторном проведении.
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
  const destinationRes = await page.request.post(`/api/warehouses/${seed.warehouseId}/locations`, {
    headers: adminHeaders,
    data: { code: `REPORT-${seed.suffix}` },
  })
  expect(destinationRes.ok()).toBeTruthy()
  const destinationId = String(((await destinationRes.json()) as { id: string }).id)
  const inboundRes = await page.request.get(`${INBOUND_API}/${rid}`, { headers: adminHeaders })
  expect(inboundRes.ok()).toBeTruthy()
  const inboundState = (await inboundRes.json()) as {
    lines: { id: string; product_id: string }[]
  }
  const lineId = inboundState.lines.find((line) => line.product_id === seed.productId)?.id
  expect(lineId).toBeTruthy()
  const locationAssignment = await page.request.patch(`${INBOUND_API}/${rid}/lines/${lineId}`, {
    headers: adminHeaders,
    data: { storage_location_id: destinationId },
  })
  expect(locationAssignment.ok()).toBeTruthy()

  await fulfillInboundViaBoxScans(page.request, adminHeaders, rid, boxes, seed.sku, [6])
  const movementPath = `${INBOUND_API}/${rid}/movements`
  const movementsBeforeVerifyRes = await page.request.get(movementPath, { headers: adminHeaders })
  expect(movementsBeforeVerifyRes.ok()).toBeTruthy()
  const movementsBeforeVerify = (await movementsBeforeVerifyRes.json()) as {
    movement_type: string
    quantity_delta: number
  }[]
  expect(movementsBeforeVerify).toHaveLength(0)

  const verify = await page.request.post(`${INBOUND_API}/${rid}/verify`, {
    headers: adminHeaders,
  })
  expect(verify.ok()).toBeTruthy()
  const movementsAfterVerifyRes = await page.request.get(movementPath, { headers: adminHeaders })
  expect(movementsAfterVerifyRes.ok()).toBeTruthy()
  const movementsAfterVerify = (await movementsAfterVerifyRes.json()) as {
    movement_type: string
    quantity_delta: number
  }[]
  const inboundMovements = movementsAfterVerify.filter(
    (movement) => movement.movement_type === 'inbound_intake',
  )
  expect(inboundMovements).toHaveLength(1)
  expect(inboundMovements[0]?.quantity_delta).toBe(6)

  const post = await page.request.post(`${INBOUND_API}/${rid}/post`, { headers: adminHeaders })
  expect(post.ok()).toBeTruthy()
  const postStateRes = await page.request.get(`${INBOUND_API}/${rid}`, { headers: adminHeaders })
  expect(postStateRes.ok()).toBeTruthy()
  const postState = (await postStateRes.json()) as {
    status: string
    lines: { posted_qty: number }[]
  }
  expect(postState.status).toBe('done')
  expect(postState.lines[0] && postState.lines[0].posted_qty).toBe(6)
  const movementsAfterPostRes = await page.request.get(movementPath, { headers: adminHeaders })
  expect(movementsAfterPostRes.ok()).toBeTruthy()
  const inboundMovementsAfterPost = (
    (await movementsAfterPostRes.json()) as { movement_type: string; quantity_delta: number }[]
  ).filter((movement) => movement.movement_type === 'inbound_intake')
  expect(inboundMovementsAfterPost).toHaveLength(1)
  expect(inboundMovementsAfterPost[0]?.quantity_delta).toBe(6)

  const duplicatePost = await page.request.post(`${INBOUND_API}/${rid}/post`, {
    headers: adminHeaders,
  })
  expect(duplicatePost.status()).toBe(409)
  const duplicatePostBody = (await duplicatePost.json()) as { detail: string }
  expect(duplicatePostBody.detail).toBe('already_posted')
  const movementsAfterRetryRes = await page.request.get(movementPath, { headers: adminHeaders })
  expect(movementsAfterRetryRes.ok()).toBeTruthy()
  const inboundMovementsAfterRetry = (
    (await movementsAfterRetryRes.json()) as { movement_type: string; quantity_delta: number }[]
  ).filter((movement) => movement.movement_type === 'inbound_intake')
  expect(inboundMovementsAfterRetry).toHaveLength(1)
  expect(inboundMovementsAfterRetry[0]?.quantity_delta).toBe(6)

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
