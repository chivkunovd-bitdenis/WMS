import { describe, expect, it } from 'vitest'
import {
  buildInboundReceivingSheetHtml,
  type InboundReceivingSheetData,
  type InboundReceivingSheetItem,
} from './printInboundReceivingSheet'

function makeItem(overrides: Partial<InboundReceivingSheetItem> = {}): InboundReceivingSheetItem {
  return {
    product_name: 'Носки хлопок',
    vendor_code: 'ART-1',
    sku_code: 'SKU-1',
    barcode: '2000000000015',
    wb_nm_id: 123456,
    photo_url: 'https://img/1.jpg',
    expected_qty: 7,
    ...overrides,
  }
}

const base: InboundReceivingSheetData = {
  documentNumber: '№000034',
  sellerName: 'ООО Ромашка',
  warehouseName: 'Склад ФФ (MSK-1)',
  plannedDate: '2026-08-19',
  items: [makeItem()],
}

describe('buildInboundReceivingSheetHtml', () => {
  it('renders A4 sheet with document header (номер, селлер, склад, дата)', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('size: A4')
    expect(html).toContain('Лист приёмки')
    expect(html).toContain('№000034')
    expect(html).toContain('ООО Ромашка')
    expect(html).toContain('Склад ФФ (MSK-1)')
    expect(html).toContain('2026-08-19')
  })

  it('renders columns in order: Фото, Товар, ШК, Заявлено, Факт', () => {
    const html = buildInboundReceivingSheetHtml(base)
    const headOrder = ['>Фото</th>', '>Товар</th>', '>ШК</th>', '>Заявлено</th>', '>Факт</th>']
    let lastIndex = -1
    for (const marker of headOrder) {
      const idx = html.indexOf(marker)
      expect(idx).toBeGreaterThan(lastIndex)
      lastIndex = idx
    }
  })

  it('renders a photo thumbnail with the passed photo url', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('<img class="rs-photo"')
    expect(html).toContain('https://img/1.jpg')
  })

  it('renders barcode and product meta (article, SKU, WB article)', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('data-testid="receiving-sheet-barcode"')
    expect(html).toContain('2000000000015')
    expect(html).toContain('ART-1')
    expect(html).toContain('123456')
  })

  it('shows the expected (заявлено) quantity from seller', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('data-testid="receiving-sheet-expected">7</td>')
  })

  it('renders an always-empty Факт cell — no digits, no placeholder', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('<td class="rs-fact-cell" data-testid="receiving-sheet-fact"></td>')
    expect(html).not.toMatch(/data-testid="receiving-sheet-fact">[^<]+</)
  })

  it('does not fill Факт even when expected_qty looks like it could be echoed', () => {
    const html = buildInboundReceivingSheetHtml({
      ...base,
      items: [makeItem({ expected_qty: 0 })],
    })
    expect(html).toContain('<td class="rs-fact-cell" data-testid="receiving-sheet-fact"></td>')
  })

  it('does not break layout for an item without a photo — renders fallback block', () => {
    const html = buildInboundReceivingSheetHtml({
      ...base,
      items: [makeItem({ photo_url: null })],
    })
    expect(html).toContain('rs-photo-empty')
    expect(html).toContain('data-testid="rs-sheet-card"')
    expect(html).not.toContain('<img class="rs-photo"')
  })

  it('falls back to SKU when vendor code is empty', () => {
    const html = buildInboundReceivingSheetHtml({
      ...base,
      items: [makeItem({ vendor_code: '', sku_code: 'SKU-XYZ' })],
    })
    expect(html).toContain('SKU-XYZ')
  })

  it('renders empty-state message when there are no items', () => {
    const html = buildInboundReceivingSheetHtml({ ...base, items: [] })
    expect(html).toContain('Нет товаров для печати')
    expect(html).not.toContain('data-testid="rs-sheet-card"')
  })

  it('keeps a row from splitting across pages', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html).toContain('page-break-inside: avoid')
  })

  it('escapes HTML in product name', () => {
    const html = buildInboundReceivingSheetHtml({
      ...base,
      items: [makeItem({ product_name: '<b>xss</b> & "q"' })],
    })
    expect(html).toContain('&lt;b&gt;xss&lt;/b&gt; &amp; &quot;q&quot;')
    expect(html).not.toContain('<b>xss</b>')
  })
})

describe('WMS-586: накладная с фактом и расхождением', () => {
  it('title replaces the generic heading', () => {
    const html = buildInboundReceivingSheetHtml({ ...base, title: 'Приёмка №000088 от 25.09.2026' })
    expect(html).toContain('<h1>Приёмка №000088 от 25.09.2026</h1>')
    expect(html).not.toContain('<h1>Лист приёмки</h1>')
  })

  it('has the Расхождение column right after Факт', () => {
    const html = buildInboundReceivingSheetHtml(base)
    expect(html.indexOf('>Расхождение</th>')).toBeGreaterThan(html.indexOf('>Факт</th>'))
  })

  it('prints fact and signed difference per line when the fact is known', () => {
    const html = buildInboundReceivingSheetHtml({
      ...base,
      items: [
        makeItem({ expected_qty: 10, actual_qty: 8 }),
        makeItem({ expected_qty: 5, actual_qty: 7 }),
        makeItem({ expected_qty: 4, actual_qty: 4 }),
      ],
    })
    const facts = [...html.matchAll(/data-testid="receiving-sheet-fact">([^<]*)</g)].map((m) => m[1])
    const diffs = [...html.matchAll(/data-testid="receiving-sheet-diff">([^<]*)</g)].map((m) => m[1])
    expect(facts).toEqual(['8', '7', '4'])
    expect(diffs).toEqual(['−2', '+2', '0'])
    expect(html.match(/rs-diff-cell rs-diff-nonzero/g)?.length).toBe(2)
  })

  it('leaves fact and difference empty before reception is closed', () => {
    const html = buildInboundReceivingSheetHtml({ ...base, items: [makeItem({ actual_qty: null })] })
    expect(html).toContain('data-testid="receiving-sheet-fact"></td>')
    expect(html).toContain('data-testid="receiving-sheet-diff"></td>')
  })
})
