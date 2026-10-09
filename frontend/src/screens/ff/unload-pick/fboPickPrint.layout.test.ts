// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { buildFboPickPrintHtml } from './fboPickPrint'
import { rowsOf } from './pickRows'
import { cellRef, objRef, type Cell, type WarehouseObject } from './pickStub'

const cells: Cell[] = [{ id: 'cell', code: 'Б-2-01', barcode: 'CELL' }]
const objects: WarehouseObject[] = [
  { id: 'pallet', kind: 'pallet', code: 'П-01', barcode: 'PALLET', holder: cellRef('cell') },
  { id: 'box', kind: 'box', code: 'К-01', barcode: 'BOX', holder: objRef('pallet') },
]
const rows = rowsOf(
  [{ id: 'line', productId: 'product', plan: 10 }],
  [{ id: 'stock', productId: 'product', qty: 12, holder: objRef('box') }],
  objects, cells, {},
  [{ id: 'product', name: 'Платье-пиджак с длинным названием и поясом', sku: 'SKU-01', sellerArticle: 'ART-01', barcode: 'PRODUCT', photo: '', size: 'M' }],
)

describe('WMS-731 R13/C18: readable FBO print layout', () => {
  it.each(['cells', 'products'] as const)('%s uses landscape A4, content-sized columns and unbroken headings', (view) => {
    const html = buildFboPickPrintHtml({ rows, objects, cells, view, selected: new Set(), document: '000002', seller: 'Селлер', marketplace: 'wb' })
    const doc = new DOMParser().parseFromString(html, 'text/html')
    const style = document.createElement('style')
    style.textContent = doc.querySelector('style')!.textContent
    document.head.appendChild(style)
    try {
      // CSS declarations are inspected; jsdom does not prove PDF page geometry.
      const rules = [...style.sheet!.cssRules] as CSSStyleRule[]
      const rule = (selector: string) => rules.find((one) => one.selectorText === selector)!.style
      expect(rule('@page').getPropertyValue('size')).toBe('A4 landscape')
      expect(rule('@page').getPropertyValue('margin')).toBe('10mm')
      expect(rule('table').getPropertyValue('table-layout')).toBe('auto')
      expect(doc.querySelector('colgroup')).toBeNull()
      expect(rule('th').getPropertyValue('white-space')).toBe('nowrap')
      expect(rule('th').getPropertyValue('overflow-wrap')).toBe('normal')
      expect(rule('th').getPropertyValue('word-break')).toBe('normal')
      expect(rule('.number').getPropertyValue('white-space')).toBe('nowrap')
      expect(rule('td').getPropertyValue('overflow-wrap')).toBe('anywhere')
      expect(rule('thead').getPropertyValue('display')).toBe('table-header-group')
      expect(rule('tr').getPropertyValue('break-inside')).toBe('avoid')
      const headings = [...doc.querySelectorAll('th')].map((node) => node.textContent)
      expect(headings).toEqual(view === 'products'
        ? ['Товар', 'Ячейка', 'Короб / тара', 'Количество, шт', 'План', 'Осталось']
        : ['Ячейка', 'Короб / тара', 'Товар', 'Количество, шт', 'План', 'Осталось'])
      const values = [...doc.querySelectorAll('tbody tr td')].map((node) => node.textContent)
      const product = 'Платье-пиджак с длинным названием и поясом · ART-01 · SKU-01 · M'
      const container = 'Палета П-01 → Короб К-01'
      expect(values).toEqual(view === 'products'
        ? [product, 'Б-2-01', container, '12', '10', '10']
        : ['Б-2-01', container, product, '12', '10', '10'])
    } finally {
      style.remove()
    }
  })
})
