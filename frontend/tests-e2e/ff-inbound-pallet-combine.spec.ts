import { expect, test } from '@playwright/test'

import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  createInboundBoxes,
  expandInboundPackages,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers'

// TC-NEW-PALLET-001 — два отмеченных короба одним действием собираются в палету.
test('inbound reception combines selected boxes into a new pallet', async ({ page }) => {
  const seed = await seedFfSellerInbound(page, `pallet-${Date.now()}`)
  const headers = { Authorization: `Bearer ${seed.token}` }
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 2,
    expectedQty: 1,
  })
  await beginInboundReceiving(page.request, headers, requestId)
  const boxes = await createInboundBoxes(page.request, headers, requestId, 2, {
    closeEach: true,
  })

  const pallet = {
    id: '10000000-0000-4000-8000-000000000001',
    code: 'П-000001',
    barcode: 'PLT-E2E-000001',
    storage_location_id: null,
    storage_location_code: null,
  }
  let combined = false
  let combineBody: Record<string, unknown> | null = null

  await page.route(`**/api/warehouses/${seed.warehouseId}/pallets?**`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })
  await page.route(`**/api/warehouses/${seed.warehouseId}/pallets/combine`, async (route) => {
    combineBody = route.request().postDataJSON() as Record<string, unknown>
    combined = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(pallet),
    })
  })
  await page.route(`**${INBOUND_API}/${requestId}`, async (route) => {
    if (route.request().method() !== 'GET' || !combined) {
      await route.fallback()
      return
    }
    const response = await route.fetch()
    const body = (await response.json()) as {
      boxes: Array<Record<string, unknown> & { id: string }>
    }
    body.boxes = body.boxes.map((box) =>
      boxes.some((candidate) => candidate.id === box.id)
        ? { ...box, pallet_id: pallet.id, pallet_code: pallet.code }
        : box,
    )
    await route.fulfill({ response, json: body })
  })

  await openFfInboundDoc(page, seed)
  await expandInboundPackages(page)

  const combineButton = page.getByTestId('ff-inbound-combine-pallet')
  await expect(combineButton).toBeDisabled()
  for (const box of boxes) {
    await page.getByTestId(`ff-inbound-box-select-${box.id}`).check()
  }
  await expect(combineButton).toBeEnabled()
  await combineButton.click()
  await expect(page.getByTestId('ff-inbound-combine-pallet-dialog')).toBeVisible()
  await expect(page.getByTestId('ff-inbound-combine-pallet-dialog')).toContainText(
    '№ 1, № 2',
  )
  await page.getByTestId('ff-inbound-combine-pallet-submit').click()

  expect(combineBody).toMatchObject({
    pallet_id: null,
    inbound_request_id: requestId,
    inbound_box_ids: boxes.map((box) => box.id),
  })
  await expect(page.getByTestId('ff-inbound-combine-pallet-dialog')).toHaveCount(0)
  for (const box of boxes) {
    await expect(page.getByTestId(`ff-inbound-box-pallet-${box.id}`)).toHaveText(
      'Палета П-000001',
    )
    await expect(page.getByTestId(`ff-inbound-box-select-${box.id}`)).toHaveCount(0)
  }
  await expect(page.getByTestId('ff-inbound-packages-toggle')).toContainText('Палеты: 1')
})
