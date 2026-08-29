import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

import { INBOUND_API, loginFfAdmin, seedFfSellerInbound } from './inbound-boxes-helpers'

const evidenceDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../docs/evidence/ozon-integration-20260825/returns',
)

test.use({ viewport: { width: 1600, height: 1000 } })

// TC-NEW-213 — возврат Ozon идёт по тому же живому потоку приёмки, что и WB, и добавляет
// к нему выбор товара, отметку брака и печать. Негатив: без выбранного товара действия недоступны.
test('Ozon return keeps the live reception flow and adds picker, defect and print actions', async ({
  page,
}) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  const suffix = `ozon-return-${Date.now()}`
  const seed = await seedFfSellerInbound(page, suffix)
  const headers = { Authorization: `Bearer ${seed.token}` }

  const create = await page.request.post(INBOUND_API, {
    headers,
    data: {
      warehouse_id: seed.warehouseId,
      seller_id: seed.sellerId,
      operation_type: 'return',
      marketplace: 'ozon',
    },
  })
  expect(create.ok()).toBeTruthy()
  const requestId = String(((await create.json()) as { id: string }).id)

  const addLine = await page.request.post(`${INBOUND_API}/${requestId}/lines`, {
    headers,
    data: { product_id: seed.productId, expected_qty: 2 },
  })
  expect(addLine.ok()).toBeTruthy()
  const lineId = String(((await addLine.json()) as { id: string }).id)

  const importedGroup = {
    giveout_id: 101,
    giveout_status: 'GIVEOUT_STATUS_APPROVED',
    warehouse_name: 'Пункт Тверская',
    warehouse_address: 'Москва, Тверская улица, 1',
    approved_articles_count: 2,
    total_articles_count: 2,
    storage_days: 4,
    utilization_forecast_date: '2026-08-29',
    already_imported: true,
    items: [
      {
        inbound_line_id: lineId,
        return_id: 5001,
        product_id: seed.productId,
        return_barcode: 'RETURN-LABEL-5001',
        offer_id: seed.vendorArticle,
        ozon_sku: 700001,
        product_name: 'Box Product',
        quantity: 2,
        approved: true,
        return_reason_name: 'Не подошёл размер',
        wms_sku: seed.sku,
        wms_barcode: seed.barcode,
        matched: true,
        warning: null,
      },
    ],
  }
  const newGroup = {
    giveout_id: 202,
    giveout_status: 'GIVEOUT_STATUS_CREATED',
    warehouse_name: 'Пункт Арбат',
    warehouse_address: 'Москва, улица Арбат, 10',
    approved_articles_count: 0,
    total_articles_count: 1,
    storage_days: 8,
    utilization_forecast_date: '2026-09-10',
    already_imported: false,
    items: [
      {
        inbound_line_id: null,
        return_id: 5002,
        product_id: null,
        return_barcode: 'RETURN-LABEL-5002',
        offer_id: 'UNKNOWN-OFFER',
        ozon_sku: 700002,
        product_name: 'Несопоставленный товар',
        quantity: 1,
        approved: false,
        return_reason_name: 'Отказ покупателя',
        wms_sku: null,
        wms_barcode: null,
        matched: false,
        warning: 'Товар не сопоставлен с каталогом',
      },
    ],
  }
  const sameProductGroup = {
    ...importedGroup,
    giveout_id: 303,
    warehouse_name: 'Пункт Сокол',
    warehouse_address: 'Москва, Ленинградский проспект, 1',
    approved_articles_count: 1,
    total_articles_count: 1,
    items: [{ ...importedGroup.items[0], return_id: 5003, quantity: 1 }],
  }
  let secondGroupImported = false

  await page.route(`**${INBOUND_API}/${requestId}/ozon-returns/groups`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        secondGroupImported
          ? [importedGroup, sameProductGroup, { ...newGroup, already_imported: true }]
          : [importedGroup, sameProductGroup],
      ),
    })
  })
  await page.route(`**${INBOUND_API}/${requestId}/ozon-returns/preview`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: true,
        message: null,
        imported_giveout_ids: secondGroupImported ? [101, 202, 303] : [101, 303],
        groups: [
          importedGroup,
          sameProductGroup,
          { ...newGroup, already_imported: secondGroupImported },
        ],
      }),
    })
  })
  await page.route(`**${INBOUND_API}/${requestId}/ozon-returns/import`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ giveout_ids: [202] })
    secondGroupImported = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        giveouts_imported: 1,
        items_imported: 1,
        unmatched_items: 1,
      }),
    })
  })
  await page.route(`**${INBOUND_API}/${requestId}/ozon-returns/pass.pdf`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/pdf',
      headers: {
        'Content-Disposition': 'attachment; filename="ozon-return-pass.pdf"',
      },
      body: '%PDF-1.4\n%%EOF',
    })
  })
  await page.addInitScript(() => {
    window.__WMS_CAPTURE_PRINT_HTML__ = true
  })

  await loginFfAdmin(page, seed.adminEmail, seed.password)
  await page.getByTestId('nav-ff-reception').click()

  await page.getByTestId('ff-inbound-create-return').click()
  await expect(page.getByTestId('ff-inbound-create-marketplace')).toContainText('Без маркетплейса')
  await page.getByTestId('ff-inbound-create-marketplace').click()
  await expect(page.getByRole('option', { name: 'Wildberries' })).toBeVisible()
  await expect(page.getByRole('option', { name: 'Ozon' })).toBeVisible()
  await expect(page.getByRole('option', { name: 'Без маркетплейса' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByTestId('ff-inbound-create-cancel').click()

  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${requestId}"]`).click()
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible()
  await expect(page.getByTestId('ff-inbound-marketplace-chip')).toHaveText('Ozon')
  await expect(page.getByTestId('ff-inbound-lines-table')).toContainText('Брак')
  await expect(page.getByTestId('ff-inbound-ozon-return-group')).toHaveCount(2)
  await expect(page.getByTestId('ff-inbound-ozon-return-group').nth(1)).toContainText('Пункт Сокол')
  await expect(page.getByTestId('ff-inbound-ozon-return-picker-open')).toBeVisible()
  await expect(page.getByTestId('ff-inbound-ozon-return-pass')).toBeVisible()
  await expect(page.getByTestId('ff-inbound-ozon-return-reconciliation')).toBeVisible()
  await page.screenshot({
    path: path.join(evidenceDir, 'document-1600.png'),
    fullPage: true,
  })

  await page.getByTestId('ff-inbound-ozon-return-picker-open').click()
  await expect(page.getByTestId('ozon-return-picker')).toBeVisible()
  await expect(page.getByTestId('ozon-return-picker-selected-count')).toHaveText(
    'Выбрано пунктов: 2 · товаров: 3',
  )
  await page.getByTestId('ozon-return-picker-select-all').click()
  await expect(page.getByTestId('ozon-return-picker-selected-count')).toHaveText(
    'Выбрано пунктов: 3 · товаров: 4',
  )
  const groups = page.getByTestId('ozon-return-picker-group')
  await groups.nth(0).locator('.MuiAccordionSummary-root').click()
  await groups.nth(1).locator('.MuiAccordionSummary-root').click()
  await groups.nth(2).locator('.MuiAccordionSummary-root').click()
  await expect(page.getByTestId('ozon-return-picker-items-table')).toHaveCount(3)
  await expect(page.getByTestId('ozon-return-picker-unmatched')).toHaveText(
    'Товар не сопоставлен с каталогом',
  )
  await expect(page.getByText('ждёт 4 дн.').first()).toBeVisible()
  await expect(page.getByText('утилизация 29.08').first()).toBeVisible()
  await page.screenshot({
    path: path.join(evidenceDir, 'picker-1600.png'),
    fullPage: true,
  })

  await page.getByTestId('ozon-return-picker-apply').click()
  await expect(page.getByTestId('ozon-return-picker')).toHaveCount(0)
  await expect(page.getByText(/Несопоставленные товары остались в документе/)).toBeVisible()
  await expect(page.getByTestId('ff-inbound-ozon-return-group')).toHaveCount(3)
  await expect(page.getByTestId('ff-inbound-ozon-return-group').nth(2)).toContainText(
    'Несопоставленный товар × 1',
  )

  await page.getByTestId('ff-inbound-ozon-return-reconciliation').click()
  await expect
    .poll(() => page.evaluate(() => window.__WMS_LAST_PRINT_HTML__ ?? ''))
    .toContain('Пункт Тверская')
  const printHtml = await page.evaluate(() => window.__WMS_LAST_PRINT_HTML__ ?? '')
  expect(printHtml.indexOf('Пункт Тверская')).toBeLessThan(printHtml.indexOf('Пункт Арбат'))

  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('ff-inbound-ozon-return-pass').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('ozon-return-pass.pdf')
})
