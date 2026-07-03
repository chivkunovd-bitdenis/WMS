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
    ...overrides,
  }
}

const base: ShipmentPackagingSheetData = {
  documentNumber: '№000034',
  sellerName: 'ООО Ромашка',
  items: [makeItem()],
}

describe('buildShipmentPackagingSheetHtml', () => {
  it('renders A4 portrait sheet with compact header (no warehouse/created)', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('size: A4 portrait')
    expect(html).toContain('ТЗ на упаковку — Отгрузка №000034')
    expect(html).toContain('ООО Ромашка')
    expect(html).not.toContain('Склад ФФ')
    expect(html).not.toContain('Создано')
    expect(html).not.toContain('Актуальная версия')
  })

  it('renders one card per item with photo, article, barcode and ТЗ text', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('data-testid="tz-sheet-card"')
    expect(html).toContain('Сложить в пакет, наклеить стикер WB')
    expect(html).toContain('ART-1')
    expect(html).toContain('2000000000015')
    expect(html).toContain('123456')
    expect(html).toContain('https://img/1.jpg')
  })

  it('renders only name, articles and barcode — no size/composition/description', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).not.toContain('Размер:')
    expect(html).not.toContain('Состав:')
  })

  it('renders product info as a highlighted block above the ТЗ block', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    const productIdx = html.indexOf('class="pk-product"')
    const tzIdx = html.indexOf('class="pk-tz"')
    expect(productIdx).toBeGreaterThan(-1)
    expect(tzIdx).toBeGreaterThan(productIdx)
    expect(html).toContain('print-color-adjust: exact')
  })

  it('keeps a card from splitting across pages', () => {
    const html = buildShipmentPackagingSheetHtml(base)
    expect(html).toContain('page-break-inside: avoid')
  })

  it('shows placeholders when ТЗ or photo missing', () => {
    const html = buildShipmentPackagingSheetHtml({
      ...base,
      items: [makeItem({ instructions: null, photo_url: null })],
    })
    expect(html).toContain('ТЗ не заполнено')
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
