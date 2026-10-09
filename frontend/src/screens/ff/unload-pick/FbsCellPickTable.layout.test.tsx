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

/** Inspect the emitted styles. jsdom cannot evaluate container queries or lay out tables. */
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

describe('WMS-731 C17: cell picking table retains readable columns at narrow widths', () => {
  it.each(['FBO', 'FBS'] as const)('%s reserves space for the first column and scrolls only when needed', (mode) => {
    styleCache = createCache({ key: 'css', speedy: false })
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
    act(() => root.render(<CacheProvider value={styleCache}><FbsCellPickTable
      rows={rows} objects={objects} cells={cells} source={null}
      onQtyChange={() => undefined} canUndo={() => false} onUndo={() => undefined}
      fbo={mode === 'FBO' ? fbo : undefined}
    /></CacheProvider>))
    const css = styleCache.sheet.tags.map((tag) => tag.textContent).join('')
    const layout = host.querySelector('[data-testid="fbs-cell-pick-layout"]')!
    expect(layout, 'table has a bounded layout container').not.toBeNull()
    const table = layout.querySelector('table')!
    const fixedWidths = [...table.querySelectorAll('thead th')].slice(1)
      .map((cell) => Number(cell.getAttribute('width')))
    expect(fixedWidths).toEqual(mode === 'FBO' ? [140, 84, 72, 96, 88, 112, 132] : [140, 84, 72, 96, 112, 132])
    const tableRules = css.match(/\.MuiTable-root\{[^}]+\}/g)?.join('') ?? ''
    const minimum = Number(/min-width:(\d+)px/.exec(tableRules)?.[1])
    expect(minimum - fixedWidths.reduce((sum, width) => sum + width, 0)).toBeGreaterThanOrEqual(320)
    expect(ownCss(layout, css)).toContain('container-type:inline-size')
    expect(ownCss(layout, css)).toContain('min-width:0')
    expect(css).toMatch(/@container[^{}]*max-width:[^{}]+\)\{[^{}]*\.MuiTableContainer-root\{overflow-x:auto;/)
    // Wide tables retain the existing header's relation to the outer document scroll.
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
})
