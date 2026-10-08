import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { fbsAssemblyPickingRows } from '../screens/v2/fbsSupplyAssembly'
import { buildFbsPickingListPrintHtml, fbsBuildPickingRows } from '../screens/v2/fbsUx'
import {
  buildInboundReceivingSheetHtml,
  type InboundReceivingSheetData,
} from './printInboundReceivingSheet'
import {
  printInboundSupplyWaybill,
  printMarketplaceUnloadWaybill,
  printOperationalOutboundWaybill,
  type ShipmentWaybillData,
} from './printShipmentWaybill'
import {
  buildShipmentPackagingSheetHtml,
  type ShipmentPackagingSheetData,
} from './printShipmentPackagingSheet'

// These are the smallest observable boundaries before the implementation:
// each helper returns (or captures) the exact HTML sent to the print iframe.
const inbound: InboundReceivingSheetData = {
  documentNumber: 'IN-680', sellerName: 'Seller A', warehouseName: 'WMS', plannedDate: '2026-10-06',
  items: [
    { product_name: 'Same article / red', vendor_code: 'ONE', sku_code: 'SKU-RED', barcode: '111', wb_nm_id: 1, photo_url: null, expected_qty: 2, size: 'S', color: 'Красный' },
    { product_name: 'Same article / blue', vendor_code: 'ONE', sku_code: 'SKU-BLUE', barcode: '222', wb_nm_id: 1, photo_url: null, expected_qty: 3, size: 'M', color: 'Синий' },
  ],
} as unknown as InboundReceivingSheetData

const packaging: ShipmentPackagingSheetData = {
  documentNumber: 'FBO-680', documentType: 'Отгрузка на МП', sellerName: 'Seller A', shipmentDate: '2026-10-06', warehouseName: 'WMS',
  items: [
    { product_name: 'WB variant', vendor_code: 'WB', sku_code: 'WB-S', barcode: '111', wb_nm_id: 1, photo_url: null, instructions: 'pack', quantity: 2, size: 'S', color: 'Красный' },
    { product_name: 'Ozon variant', vendor_code: 'OZ', sku_code: 'OZ-M', barcode: '222', wb_nm_id: 2, photo_url: null, instructions: 'pack', quantity: 3, size: 'M', color: 'Синий' },
  ],
} as unknown as ShipmentPackagingSheetData

function waybill(kind: ShipmentWaybillData['docKind']): ShipmentWaybillData {
  return {
    docKind: kind, documentId: 'outbound-680', documentNumber: 'OUT-680', waybillNumber: 'WB-680', documentTypeLabel: 'Возврат',
    statusLabel: 'draft', warehouseName: 'WMS', sellerName: 'Seller A', wbWarehouseLabel: 'Коледино', plannedDate: '2026-10-06', createdAt: '2026-10-06',
    lines: [
      { sku_code: 'SKU-S', product_name: 'Variant S', quantity: 2, shipped_qty: 1, received_qty: 0, storage_location_code: 'A-01', size: 'S', color: 'Красный' },
      { sku_code: 'SKU-M', product_name: 'Variant M', quantity: 3, shipped_qty: 2, received_qty: 1, storage_location_code: 'B-02', size: 'M', color: 'Синий' },
    ],
    pickAllocations: [{ location_code: 'A-01', sku_code: 'SKU-S', quantity: 2 }],
  } as unknown as ShipmentWaybillData
}

function capturedWaybill(kind: ShipmentWaybillData['docKind']) {
  const state = globalThis as { window?: unknown; document?: unknown }
  const previousWindow = state.window
  const previousDocument = state.document
  const capture = { __WMS_CAPTURE_PRINT_HTML__: true, __WMS_LAST_PRINT_HTML__: '' }
  const iframe = { setAttribute() {}, style: {}, onload: null } as unknown as HTMLIFrameElement
  state.window = capture
  state.document = {
    createElement: () => iframe,
    body: { appendChild() {}, removeChild() {} },
  } as unknown as Document
  try {
    const data = waybill(kind)
    if (kind === 'marketplace_unload') printMarketplaceUnloadWaybill({ ...data, wbWarehouseLabel: data.wbWarehouseLabel ?? null })
    else if (kind === 'operational_outbound') printOperationalOutboundWaybill(data)
    else printInboundSupplyWaybill(data)
    return capture.__WMS_LAST_PRINT_HTML__
  } finally {
    state.window = previousWindow
    state.document = previousDocument
  }
}

function expectOwnVariantRows(html: string) {
  expect(html).toContain('Размер')
  expect(html).toContain('Цвет')
  const first = html.indexOf('Variant S')
  const second = html.indexOf('Variant M')
  expect(first).toBeGreaterThan(-1)
  expect(second).toBeGreaterThan(first)
  expect(html.slice(first, second)).toContain('S')
  expect(html.slice(first, second)).toContain('Красный')
  expect(html.slice(second)).toContain('M')
  expect(html.slice(second)).toContain('Синий')
}

type VariantColumns = { article: string; color: string; size: string }

function printableText(fragment: string) {
  return fragment
    .replace(/<[^>]*>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim()
}

function mainTable(html: string) {
  const table = html.match(/<table\b[^>]*>[\s\S]*?<\/table>/)?.[0]
  expect(table, 'печатная форма должна содержать товарную таблицу').toBeTruthy()
  return table!
}

function tableHeaders(html: string) {
  return [...mainTable(html).matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)].map((match) => printableText(match[1]!))
}

function tableRows(html: string) {
  const body = mainTable(html).match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1]
  expect(body, 'товарная таблица должна содержать tbody').toBeTruthy()
  return [...body!.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((match) => match[1]!)
}

function rowCells(row: string) {
  return [...row.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map((match) => printableText(match[1]!))
}

function productCellText(items: Array<{ product_name: string; vendor_code: string; sku_code: string; wb_nm_id: number | null }>) {
  return items.map((item) => {
    const article = item.vendor_code.trim() || item.sku_code.trim() || '—'
    const meta = [
      item.sku_code.trim() && item.sku_code.trim() !== article ? `SKU: ${item.sku_code.trim()}` : '',
      item.wb_nm_id != null ? `Артикул WB: ${item.wb_nm_id}` : '',
    ].filter(Boolean).join(' · ')
    return `${item.product_name}${meta ? ` ${meta}` : ''}`
  })
}

/** R8 replaces only the old inline placement, not the values or their sources. */
function expectSeparateVariantColumns(html: string, expected: VariantColumns[], expectedProductCells: string[]) {
  const headers = tableHeaders(html)
  for (const header of ['Артикул', 'Цвет', 'Размер']) {
    expect(headers.filter((value) => value === header), `ровно один столбец «${header}»`).toHaveLength(1)
  }
  const article = headers.indexOf('Артикул')
  const color = headers.indexOf('Цвет')
  const size = headers.indexOf('Размер')
  const product = headers.findIndex((value) => /товар|наименование/i.test(value))
  expect(product, 'название товара остаётся отдельным текстовым столбцом').toBeGreaterThanOrEqual(0)
  const rows = tableRows(html)
  expect(rows).toHaveLength(expected.length)
  expect(expectedProductCells).toHaveLength(expected.length)
  for (const [index, values] of expected.entries()) {
    const cells = rowCells(rows[index]!)
    expect(cells).toHaveLength(headers.length)
    expect(cells[article]).toBe(values.article)
    expect(cells[color]).toBe(values.color)
    expect(cells[size]).toBe(values.size)
    // The exact product cell preserves a lawful name/SKU/WB article even if its text
    // happens to contain a color word, an article word, or a digit equal to a size.
    // A historical inline variant would make this structural cell assertion fail.
    expect(cells[product]).toBe(expectedProductCells[index])
  }
}

const fourVariants: VariantColumns[] = [
  { article: 'ART-680', color: 'COLOR-RED-680', size: 'SIZE-S-680' },
  { article: 'ART-680', color: 'COLOR-BLUE-680', size: 'SIZE-M-680' },
  { article: 'ART-680', color: 'COLOR-GREEN-680', size: 'SIZE-L-680' },
  { article: 'ART-680', color: 'COLOR-BLACK-680', size: 'SIZE-XL-680' },
]

function fourInboundRows() {
  return fourVariants.map((variant, index) => ({
    product_name: `NAME-${index + 1}-680`, vendor_code: variant.article, sku_code: `SKU-${index + 1}-680`,
    barcode: `00000000000${index + 1}`, wb_nm_id: 680 + index, photo_url: null,
    expected_qty: index + 1, size: variant.size, color: variant.color,
  }))
}

function fourPackagingRows() {
  return fourVariants.map((variant, index) => ({
    product_name: `PACK-NAME-${index + 1}-680`, vendor_code: variant.article, sku_code: `PACK-SKU-${index + 1}-680`,
    barcode: `10000000000${index + 1}`, wb_nm_id: 690 + index, photo_url: null,
    instructions: `INSTRUCTION-${index + 1}-680`, quantity: index + 1, size: variant.size, color: variant.color,
  }))
}

function fourWaybill(kind: ShipmentWaybillData['docKind']) {
  return {
    ...waybill(kind),
    lines: fourVariants.map((variant, index) => ({
      sku_code: variant.article, product_name: `WAYBILL-NAME-${index + 1}-680`, quantity: index + 1,
      shipped_qty: index, received_qty: index, storage_location_code: `CELL-${index + 1}-680`,
      size: variant.size, color: variant.color,
    })),
  } as ShipmentWaybillData
}

function capturedWaybillData(data: ShipmentWaybillData) {
  const state = globalThis as { window?: unknown; document?: unknown }
  const previousWindow = state.window
  const previousDocument = state.document
  const capture = { __WMS_CAPTURE_PRINT_HTML__: true, __WMS_LAST_PRINT_HTML__: '' }
  const iframe = { setAttribute() {}, style: {}, onload: null } as unknown as HTMLIFrameElement
  state.window = capture
  state.document = { createElement: () => iframe, body: { appendChild() {}, removeChild() {} } } as unknown as Document
  try {
    if (data.docKind === 'marketplace_unload') printMarketplaceUnloadWaybill({ ...data, wbWarehouseLabel: data.wbWarehouseLabel ?? null })
    else if (data.docKind === 'operational_outbound') printOperationalOutboundWaybill(data)
    else printInboundSupplyWaybill(data)
    return capture.__WMS_LAST_PRINT_HTML__
  } finally {
    state.window = previousWindow
    state.document = previousDocument
  }
}

describe('WMS-680 · контракт печатных накладных до реализации', () => {
  it('C680-01: лист приёмки и возврат печатают варианты своих Product без смешения строк', () => {
    const html = buildInboundReceivingSheetHtml(inbound)
    expectOwnVariantRows(html.replaceAll('Same article / red', 'Variant S').replaceAll('Same article / blue', 'Variant M'))
    expect(html).toContain('data-testid="receiving-sheet-expected">2</td>')
    expect(html).toContain('data-testid="receiving-sheet-fact"></td>')
  })

  it('C680-02: реальная FBO-форма WB и Ozon сохраняет варианты каждой строки', () => {
    const html = buildShipmentPackagingSheetHtml(packaging)
    expect(html).toContain('WB variant')
    expect(html).toContain('Ozon variant')
    expect(html).toContain('Размер')
    expect(html).toContain('Цвет')
    expect(html).toContain('data-testid="tz-sheet-qty">2</td>')
    expect(html).toContain('data-testid="shipment-sheet-fact"></td>')
  })

  it('C680-03: самостоятельная упаковка использует ту же форму и не теряет два поля', () => {
    const html = buildShipmentPackagingSheetHtml(packaging)
    expect(html).toContain('WB variant')
    expect(html).toContain('S')
    expect(html).toContain('Красный')
  })

  it('C680-04: операционная отгрузка сохраняет ячейки, подбор и варианты строк', () => {
    const html = capturedWaybill('operational_outbound')
    expectOwnVariantRows(html)
    expect(html).toContain('<th>Ячейка</th>')
    expect(html).toContain('Подбор по ячейкам')
    expect(html).toContain('A-01')
    expect(html).toContain('Отгружено')
  })

  it('C680-05: WB, многопозиционный Ozon и групповая сборка сохраняют size/color позиции', () => {
    const ozon = {
      id: 'ozon-680', wb_order_id: 680, tape_order_index: 0,
      product: { id: 'root', name: 'root must not win', size: 'ROOT', color: 'ROOT', image_url: null, seller_article: null, wb_article: null, barcode: null },
      positions: [
        { id: 'one', product_id: 'one', name: 'Ozon one', size: 'M', color: 'Синий', image_url: null, seller_article: 'OZ-1', sku: 'OZ-1', barcode: null, marketplace_bindings: [], quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
        { id: 'two', product_id: 'two', name: 'Ozon two', size: 'L', color: 'Зелёный', image_url: null, seller_article: 'OZ-2', sku: 'OZ-2', barcode: null, marketplace_bindings: [], quantity: 2, reserved_quantity: 2, picked_quantity: 0 },
      ], metadata: { required: [] }, pick: { status: 'pending' }, sticker: { code: null }, inventory: { locations: [] }, deadline_at: '2026-10-07',
    }
    const wb = { ...ozon, id: 'wb-680', wb_order_id: 681, positions: [], product: { ...ozon.product, id: 'wb', name: 'WB one', size: 'S', color: 'Красный' } }
    const { rows } = fbsBuildPickingRows([wb, ozon] as never, true)
    expect(rows).toMatchObject([{ name: 'Ozon one', size: 'M', color: 'Синий' }, { name: 'Ozon two', size: 'L', color: 'Зелёный' }])
    const assemblyRows = fbsAssemblyPickingRows([{ orders: [ozon] }] as never)
    expect(assemblyRows).toMatchObject([{ name: 'Ozon one', size: 'M', color: 'Синий' }, { name: 'Ozon two', size: 'L', color: 'Зелёный' }])
    const html = buildFbsPickingListPrintHtml({
      supplyName: 'FBS-680', wbSupplyId: 'WB-680', marketplace: 'mixed', sellerName: 'Seller A', wmsWarehouseName: 'WMS',
      routeLabel: 'Route', deadlineLabel: '2026-10-07', printedAtLabel: '2026-10-06',
      rows: [{ name: 'WB one', size: 'S', color: 'Красный', imageUrl: null, identifiers: [], locations: [], required: 1, picked: 0, wbOrders: [681], stickerCodes: [null], marking: '—' },
        { name: 'Ozon one', size: 'M', color: 'Синий', imageUrl: null, identifiers: [], locations: [], required: 1, picked: 0, wbOrders: [680], stickerCodes: [null], marking: '—' }],
    } as unknown as Parameters<typeof buildFbsPickingListPrintHtml>[0])
    expect(html).toContain('Цвет')
    expect(html).toContain('Красный')
    expect(html).toContain('Синий')
  })

  it.each(['marketplace_unload', 'operational_outbound', 'inbound_intake'] as const)(
    'C680-06: общая форма %s показывает оба подписанных поля без потери реквизитов',
    (kind) => {
      const html = capturedWaybill(kind)
      expectOwnVariantRows(html)
      expect(html).toContain('Seller A')
      expect(html).toContain('2026-10-06')
    },
  )

  it('C680-08: известные поля строки доходят до печати без каталожной подстановки или блокировки', () => {
    const htmlWithoutCatalog = buildShipmentPackagingSheetHtml({
      ...packaging,
      items: [{ ...packaging.items[0]!, size: 'KNOWN-S', color: 'KNOWN-RED' }],
    } as unknown as ShipmentPackagingSheetData)
    expect(htmlWithoutCatalog).toContain('KNOWN-S')
    expect(htmlWithoutCatalog).toContain('KNOWN-RED')
    expect(htmlWithoutCatalog).not.toContain('catalog')
  })

  it.each([
    [undefined, 'Blue', '—', 'Blue'], [null, 'Blue', '—', 'Blue'], ['', 'Blue', '—', 'Blue'], ['   ', 'Blue', '—', 'Blue'],
    ['0', null, '0', '—'], ['S', 'Red & <Blue>', 'S', 'Red &amp; &lt;Blue&gt;'],
  ])('C680-09/C680-10: пустые поля независимы, 0 и HTML остаются корректными (%o, %o)', (size, color, expectedSize, expectedColor) => {
    const html = buildShipmentPackagingSheetHtml({
      ...packaging,
      items: [{ ...packaging.items[0]!, size, color }],
    } as unknown as ShipmentPackagingSheetData)
    expect(html).toContain(expectedSize)
    expect(html).toContain(expectedColor)
    expect(html).toContain('pack')
    expect(html).toContain('data-testid="tz-sheet-qty">2</td>')
  })

  it('C680-11: генерация дважды не меняет документ и не переносит вариант в другой документ', () => {
    const first = JSON.parse(JSON.stringify(inbound)) as InboundReceivingSheetData
    const second = { ...inbound, documentNumber: 'IN-681', items: [{ ...inbound.items[1]!, size: 'XL', color: 'Чёрный' }] } as unknown as InboundReceivingSheetData
    const beforeFirst = JSON.stringify(first)
    const beforeSecond = JSON.stringify(second)
    const firstHtml = buildInboundReceivingSheetHtml(first)
    const secondHtml = buildInboundReceivingSheetHtml(second)
    expect(JSON.stringify(first)).toBe(beforeFirst)
    expect(JSON.stringify(second)).toBe(beforeSecond)
    expect(firstHtml).toContain('Красный')
    expect(secondHtml).toContain('Чёрный')
    expect(secondHtml).not.toContain('Красный')
  })

  it('C680-12: инвентаризированные печатные входы остаются отдельными от акта, стикеров и WMS-679', () => {
    const paths = [
      'frontend/src/screens/ff/FfInboundRequestView.tsx',
      'frontend/src/screens/ff/FfPackagingPage.tsx',
      'frontend/src/screens/v2/OutboundScreen.tsx',
      'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx',
      'frontend/src/screens/v2/FfFbsSupplyAssembly.tsx',
    ]
    const sources = paths.map((path) => readFileSync(new URL(`../../../${path}`, import.meta.url), 'utf8'))
    const source = sources.join('\n')
    for (const entry of ['printInboundReceivingSheet', 'printShipmentPackagingSheet', 'printOperationalOutboundWaybill', 'buildFbsPickingListPrintHtml']) {
      expect(source).toContain(entry)
    }
    expect(source).not.toContain('WMS-680: acceptance-act')
    expect(source).not.toContain('WMS-680: print-label')
  })

  it('C680-15: все реальные шаблоны печатают четыре варианта в отдельных столбцах Артикул, Цвет и Размер', () => {
    const inboundRows = fourInboundRows()
    const packagingRows = fourPackagingRows()
    const inboundHtml = buildInboundReceivingSheetHtml({ ...inbound, items: inboundRows } as InboundReceivingSheetData)
    const packagingHtml = buildShipmentPackagingSheetHtml({ ...packaging, items: packagingRows } as ShipmentPackagingSheetData)
    expectSeparateVariantColumns(inboundHtml, fourVariants, productCellText(inboundRows))
    expectSeparateVariantColumns(packagingHtml, fourVariants, productCellText(packagingRows))

    for (const kind of ['marketplace_unload', 'operational_outbound', 'inbound_intake'] as const) {
      const data = fourWaybill(kind)
      expectSeparateVariantColumns(capturedWaybillData(data), fourVariants, data.lines.map((line) => line.product_name))
    }

    const fbsRows = fourVariants.map((variant, index) => ({
      name: `FBS-NAME-${index + 1}-680`, size: variant.size, color: variant.color, imageUrl: null,
      identifiers: [variant.article, `BARCODE-${index + 1}-680`], locations: [`FBS-CELL-${index + 1}-680`],
      required: index + 10, picked: index, wbOrders: [6800 + index], stickerCodes: [null], marking: `MARK-${index + 1}-680`,
    }))
    const fbsHtml = buildFbsPickingListPrintHtml({
      supplyName: 'FBS-680-columns', wbSupplyId: 'WB-680', marketplace: 'mixed', sellerName: 'Seller A', wmsWarehouseName: 'WMS',
      routeLabel: 'Route', deadlineLabel: '2026-10-07', printedAtLabel: '2026-10-06',
      rows: fbsRows,
    })
    expectSeparateVariantColumns(fbsHtml, fourVariants, fbsRows.map((row) => `${row.name} ${row.identifiers[1]!}`))
  })

  it('C680-16: известные, fallback, whitespace и строковый 0 остаются в собственных колонках без каталога', () => {
    const expected = [
      { article: 'KNOWN-ARTICLE-680', color: 'KNOWN-COLOR-680', size: '0' },
      { article: 'SKU-FALLBACK-680', color: '—', size: '—' },
    ]
    const inboundItems = [
      { ...fourInboundRows()[0]!, product_name: 'NAME-0 KNOWN-ARTICLE-680 KNOWN-COLOR-680', vendor_code: expected[0]!.article, sku_code: 'SKU-KNOWN-680', color: expected[0]!.color, size: expected[0]!.size },
      { ...fourInboundRows()[1]!, vendor_code: '   ', sku_code: expected[1]!.article, color: '  ', size: '   ' },
    ]
    const packagingItems = [
      { ...fourPackagingRows()[0]!, product_name: 'NAME-0 KNOWN-ARTICLE-680 KNOWN-COLOR-680', vendor_code: expected[0]!.article, sku_code: 'SKU-KNOWN-680', color: expected[0]!.color, size: expected[0]!.size },
      { ...fourPackagingRows()[1]!, vendor_code: '   ', sku_code: expected[1]!.article, color: '  ', size: '   ' },
    ]
    const inboundHtml = buildInboundReceivingSheetHtml({
      ...inbound,
      items: inboundItems,
    } as InboundReceivingSheetData)
    const packagingHtml = buildShipmentPackagingSheetHtml({
      ...packaging,
      items: packagingItems,
    } as ShipmentPackagingSheetData)
    expectSeparateVariantColumns(inboundHtml, expected, productCellText(inboundItems))
    expectSeparateVariantColumns(packagingHtml, expected, productCellText(packagingItems))

    for (const kind of ['marketplace_unload', 'operational_outbound', 'inbound_intake'] as const) {
      const data = fourWaybill(kind)
      data.lines = [
        { ...data.lines[0]!, sku_code: expected[0]!.article, color: expected[0]!.color, size: expected[0]!.size },
        { ...data.lines[1]!, sku_code: expected[1]!.article, color: '  ', size: '   ' },
      ]
      expectSeparateVariantColumns(capturedWaybillData(data), expected, data.lines.map((line) => line.product_name))
    }

    const fbsRows = expected.map((variant, index) => ({
      name: `FBS-FALLBACK-${index + 1}-680`, size: variant.size === '—' ? '  ' : variant.size,
      color: variant.color === '—' ? '  ' : variant.color, imageUrl: null, identifiers: [variant.article], locations: [],
      required: index + 100, picked: 0, wbOrders: [6900 + index], stickerCodes: [null], marking: '—',
    }))
    const fbsHtml = buildFbsPickingListPrintHtml({
      supplyName: 'FBS-680-fallback', wbSupplyId: 'WB-680', marketplace: 'ozon', sellerName: 'Seller A', wmsWarehouseName: 'WMS',
      routeLabel: 'Route', deadlineLabel: '2026-10-07', printedAtLabel: '2026-10-06',
      rows: fbsRows,
    })
    expectSeparateVariantColumns(fbsHtml, expected, fbsRows.map((row) => row.name))

    const lawfulName = 'NAME-0 KNOWN-ARTICLE-680 KNOWN-COLOR-680'
    const structurallySeparate = `<table><thead><tr><th>Товар</th><th>Артикул</th><th>Цвет</th><th>Размер</th></tr></thead><tbody><tr><td>${lawfulName}</td><td>KNOWN-ARTICLE-680</td><td>KNOWN-COLOR-680</td><td>0</td></tr></tbody></table>`
    expectSeparateVariantColumns(structurallySeparate, [expected[0]!], [lawfulName])
    const historicalInline = `<table><thead><tr><th>Товар</th></tr></thead><tbody><tr><td>${lawfulName}<span data-legacy-inline="article">KNOWN-ARTICLE-680</span><span data-legacy-inline="color">KNOWN-COLOR-680</span><span data-legacy-inline="size">0</span></td></tr></tbody></table>`
    expect(() => expectSeparateVariantColumns(historicalInline, [expected[0]!], [lawfulName])).toThrow(/столбец «Артикул»/)
  })

  it('C680-17: реальные caller-map сохраняют варианты, реквизиты и границы прежних форм', () => {
    const files = {
      inbound: readFileSync(new URL('../../../frontend/src/screens/ff/FfInboundRequestView.tsx', import.meta.url), 'utf8'),
      packaging: readFileSync(new URL('../../../frontend/src/screens/ff/FfPackagingPage.tsx', import.meta.url), 'utf8'),
      outbound: readFileSync(new URL('../../../frontend/src/screens/v2/OutboundScreen.tsx', import.meta.url), 'utf8'),
      workspace: readFileSync(new URL('../../../frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx', import.meta.url), 'utf8'),
      assembly: readFileSync(new URL('../../../frontend/src/screens/v2/FfFbsSupplyAssembly.tsx', import.meta.url), 'utf8'),
    }
    expect(files.inbound).toContain('vendor_code: meta.wb_vendor_code ?? \'\'')
    expect(files.inbound).toContain('size: ln.size')
    expect(files.inbound).toContain('color: ln.color')
    expect(files.packaging).toContain('vendor_code: displayMeta.wb_vendor_code ?? \'\'')
    expect(files.packaging).toContain('instructions: ln.packaging_instructions')
    expect(files.packaging).toContain('quantity: ln.qty_need_pack')
    expect(files.outbound).toContain('storage_location_code: addressStorageEnabled')
    expect(files.outbound).toContain('shipped_qty: ln.shipped_qty')
    expect(files.workspace).toMatch(/let rows = fbsBuildPickingRows\(\s*printWorkspace\.orders,\s*printWorkspace\.supply\.marketplace === 'ozon',\s*\)\.rows/)
    expect(files.assembly).toContain('let rows = fbsAssemblyPickingRows(printable)')

    const html = buildShipmentPackagingSheetHtml({ ...packaging, items: fourPackagingRows() } as ShipmentPackagingSheetData)
    for (const value of ['100000000001', 'INSTRUCTION-1-680', '1', 'data-testid="shipment-sheet-fact"></td>', 'size: A4']) {
      expect(html).toContain(value)
    }
    const operational = capturedWaybillData(fourWaybill('operational_outbound'))
    for (const value of ['CELL-1-680', 'Подбор по ячейкам', 'Отгружено', 'Seller A']) expect(operational).toContain(value)
  })
})
