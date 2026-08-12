import { describe, expect, it } from 'vitest'
import {
  buildShipmentPackagingSheetHtml,
  type PackagingSheetItem,
  type ShipmentPackagingSheetData,
} from './printShipmentPackagingSheet'

function makeItem(overrides: Partial<PackagingSheetItem> = {}): PackagingSheetItem {
  return {
    product_name: 'Носки хлопок',
    vendor_code: 'ART-1',
    sku_code: 'SKU-1',
    barcode: '2000000000015',
    wb_nm_id: 123456,
    photo_url: 'https://img/1.jpg',
    instructions: 'Сложить в пакет, наклеить стикер WB',
    quantity: 3,
    ...overrides,
  }
}

const base: ShipmentPackagingSheetData = {
  documentNumber: '№000034',
  documentType: 'Отгрузка на МП',
  sellerName: 'ООО Ромашка',
  shipmentDate: '2026-08-12',
  warehouseName: 'Склад ФФ',
  marketplaceWarehouseName: 'Коледино (507)',
  createdAt: '12.08.2026, 10:30',
  items: [makeItem()],
}

describe('buildShipmentPackagingSheetHtml', () => {
  it('renders A4 sheet (orientation chosen in print dialog, not forced in CSS)', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('size: A4')
    expect(html).not.toContain('size: A4 landscape')
    expect(html).toContain('Лист отгрузки')
    expect(html).toContain('ООО Ромашка')
    expect(html).toContain('2026-08-12')
    expect(html).toContain('Отгрузка на МП')
    expect(html).toContain('№000034')
    expect(html).toContain('Склад ФФ')
    expect(html).toContain('Коледино (507)')
    expect(html).not.toContain('Создано')
    expect(html).not.toContain('Актуальная версия')
  })

  it('renders shipment line quantity in a dedicated column', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('data-testid="tz-sheet-qty"')
    expect(html).toContain('<th>Кол-во</th>')
    expect(html).toContain('data-testid="tz-sheet-qty">3</td>')
  })

  it('renders one row per item with photo, article, barcode and instructions', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('data-testid="tz-sheet-card"')
    expect(html).toContain('Сложить в пакет, наклеить стикер WB')
    expect(html).toContain('ART-1')
    expect(html).toContain('2000000000015')
    expect(html).toContain('123456')
    expect(html).toContain('https://img/1.jpg')
  })

  it('renders barcode on a separate bold line in the product header', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('data-testid="shipment-sheet-barcode"')
    expect(html).toContain('>2000000000015</td>')
    expect(html).not.toContain('ШК: 2000000000015')
  })

  it('renders only name, articles and barcode — no size/composition/description', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).not.toContain('Размер:')
    expect(html).not.toContain('Состав:')
  })

  it('renders a compact table with an empty Fact column', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('data-testid="shipment-sheet-table"')
    expect(html).toContain('<th>Факт</th>')
    expect(html).toContain('data-testid="shipment-sheet-fact"')
    expect(html).toContain('print-color-adjust: exact')
  })

  it('keeps a row from splitting across pages', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('page-break-inside: avoid')
  })

  it('shows placeholders when ТЗ or photo missing', () => {
    const html = buildShipmentPackagingSheetHtml({
      ...base,
      items: [makeItem({ instructions: null, photo_url: null })],
    })
    expect(html).toContain('Инструкция не заполнена')
    expect(html).toContain('pk-photo-empty')
  })

  it('falls back to SKU when vendor code empty', () => {
    const html = buildShipmentPackagingSheetHtml({
      ...base,
      items: [makeItem({ vendor_code: '', sku_code: 'SKU-XYZ' })],
    })
    expect(html).toContain('SKU-XYZ')
  })

  it('renders empty-state message when no items', () => {
    const html = buildShipmentPackagingSheetHtml({ ...base, items: [] })
    expect(html).toContain('Нет товаров для печати')
    expect(html).not.toContain('data-testid="tz-sheet-card"')
  })

  it('escapes HTML in ТЗ text', () => {
    const html = buildShipmentPackagingSheetHtml({
      ...base,
      items: [makeItem({ instructions: '<b>xss</b> & "q"' })],
    })
    expect(html).toContain('&lt;b&gt;xss&lt;/b&gt; &amp; &quot;q&quot;')
    expect(html).not.toContain('<b>xss</b>')
  })
})
