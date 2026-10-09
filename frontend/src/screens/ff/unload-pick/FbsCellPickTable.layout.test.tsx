// @vitest-environment jsdom
import createCache from '@emotion/cache'
import { CacheProvider } from '@emotion/react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { FbsCellPickTable, type FbsCellPickFbo } from './FbsCellPickTable'
import { rowsOf } from './pickRows'
import { cellRef, objRef, type Cell, type WarehouseObject } from './pickStub'

const cells: Cell[] = [{ id: 'cell', code: 'Ячейка-с-очень-длинным-адресом', barcode: 'CELL' }]
const objects: WarehouseObject[] = [
  { id: 'pallet', kind: 'pallet', code: 'Длинный-номер-палеты', barcode: 'PALLET', holder: cellRef('cell') },
  { id: 'box', kind: 'box', code: 'Длинный-номер-вложенного-короба', barcode: 'BOX', holder: objRef('pallet') },
]
const rows = rowsOf(
  [{ id: 'line', productId: 'product', plan: 10 }],
  [{ id: 'stock', productId: 'product', qty: 12, holder: objRef('box') }],
  objects, cells, {},
  [{ id: 'product', name: 'Товар с длинным названием и размером', sku: 'ОченьДлинныйАртикулБезПробелов', sellerArticle: '', barcode: 'PRODUCT', photo: '', size: 'Универсальный' }],
)
const fbo: FbsCellPickFbo = {
  collapsed: new Set(), onToggleCollapsed: () => undefined,
  kizCodes: [], markingProducts: new Set(), kizOpen: new Set(),
  onToggleKiz: () => undefined, onKizRemove: async () => undefined, onKizReprint: async () => undefined,
  printSelection: { selected: new Set(), onToggle: () => undefined },
}

/** Inspect the emitted styles. jsdom cannot prove scroll geometry or lay out tables. */
function ownCss(element: Element, css: string): string {
  return [...element.classList].filter((name) => name.startsWith('css-'))
    .flatMap((name) => [...css.matchAll(new RegExp(`\\.${name}\\{([^}]+)\\}`, 'g'))].map((match) => match[1]))
    .join(';')
}

let styleCache: ReturnType<typeof createCache>
let root: Root
let host: HTMLDivElement
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
afterEach(() => {
  act(() => root?.unmount())
  host?.remove()
  styleCache?.sheet.flush()
})

function mountTable(mode: 'FBO' | 'FBS'): string {
  styleCache = createCache({ key: 'css', speedy: false })
  host = document.createElement('div')
  // Model the existing DialogContent/page scroll area, not an inner table scroll.
  host.style.cssText = 'width:800px;height:600px;overflow:auto'
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => root.render(<CacheProvider value={styleCache}><FbsCellPickTable
    rows={rows} objects={objects} cells={cells} source={null}
    onQtyChange={() => undefined} canUndo={() => false} onUndo={() => undefined}
    fbo={mode === 'FBO' ? fbo : undefined}
  /></CacheProvider>))
  return styleCache.sheet.tags.map((tag) => tag.textContent).join('')
}

describe('WMS-731 C17: cell picking table retains readable columns at narrow widths', () => {
  it.each(['FBO', 'FBS'] as const)('%s reserves readable width and lets the outer area scroll the full table', (mode) => {
    const css = mountTable(mode)
    const layout = host.querySelector('[data-testid="fbs-cell-pick-layout"]')!
    expect(layout, 'table has a bounded layout container').not.toBeNull()
    const table = layout.querySelector('table')!
    const fixedWidths = [...table.querySelectorAll('thead th')].slice(1)
      .map((cell) => Number(cell.getAttribute('width')))
    expect(fixedWidths).toEqual(mode === 'FBO' ? [140, 84, 72, 96, 88, 112, 132] : [140, 84, 72, 96, 112, 132])
    const tableRules = css.match(/\.MuiTable-root\{[^}]+\}/g)?.join('') ?? ''
    const minimum = Number(/min-width:(\d+)px/.exec(tableRules)?.[1])
    expect(minimum - fixedWidths.reduce((sum, width) => sum + width, 0)).toBeGreaterThanOrEqual(320)
    // The Paper grows with its table so the background/border include all columns.
    expect(css).toContain(`.MuiTableContainer-root{min-width:${minimum}px;}`)
    expect(ownCss(layout, css)).toContain('container-type:inline-size')
    expect(ownCss(layout, css)).toContain('min-width:0')
    // The same outer area handles both axes at narrow and wide widths.
    expect(host.style.overflow).toBe('auto')
    expect(css).toContain('overflow:visible;')
    expect(table.querySelector('th')?.textContent).toBe('Ячейка / тара / товар')
    for (const key of ['cell:cell', 'obj:pallet', 'obj:box', 'line|obj:box']) {
      const item = host.querySelector(`[data-testid="fbs-pick-item-${key}"]`)!
      expect(item).not.toBeNull()
      expect(ownCss(item, css)).toContain('min-width:0')
      const label = [...item.querySelectorAll('.MuiTypography-root')].find((node) => node.tagName !== 'SPAN')!
      const labelRules = ownCss(label, css)
      expect(labelRules).toContain('min-width:0')
      expect(labelRules).toContain('white-space:normal')
      expect(labelRules).toContain('overflow-wrap:anywhere')
    }
    expect(host.querySelectorAll('input[data-testid^="pick-place-qty-"]')).toHaveLength(1)
    expect(host.querySelectorAll('input[type="checkbox"]').length > 0).toBe(mode === 'FBO')
  })

  it.each(['FBO', 'FBS'] as const)('%s keeps sticky headings attached to the external scroll area on both axes', (mode) => {
    const css = mountTable(mode)
    const layout = host.querySelector('[data-testid="fbs-cell-pick-layout"]')!
    const container = layout.querySelector('.MuiTableContainer-root')!
    expect(container.parentElement).toBe(layout)
    expect(layout.parentElement).toBe(host)
    expect(host.style.overflow).toBe('auto')
    expect(ownCss(layout, css)).not.toMatch(/overflow(?:-[xy])?:(auto|scroll|hidden)/)
    expect(ownCss(container, css)).toMatch(/overflow:visible;/)
    // An overflow-x override would also change computed overflow-y to auto and
    // steal sticky positioning from DialogContent, even without a height limit.
    const scrollingOverrides = css.match(/\.MuiTableContainer-root\{[^}]*overflow(?:-[xy])?:(auto|scroll|hidden)/g) ?? []
    expect(scrollingOverrides).toEqual([])
    for (const heading of container.querySelectorAll('th')) {
      const rules = ownCss(heading, css)
      expect(rules).toContain('position:sticky')
      expect(rules).toContain('top:0')
      expect(rules).toContain('z-index:3')
      expect(rules).toMatch(/background-color:(?!transparent)[^;]+;/)
    }
  })
})
