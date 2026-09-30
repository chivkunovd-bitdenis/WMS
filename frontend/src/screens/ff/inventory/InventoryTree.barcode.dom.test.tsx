// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import type { InvRow } from './InventoryRows'
import { InventoryTree } from './InventoryTree'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

function product(
  id: string,
  barcode: string | null,
  wbBarcode: string | null,
): InvRow {
  return {
    key: `product:${id}`,
    id,
    kind: 'product',
    depth: 0,
    title: id,
    seller: 'Селлер',
    category: null,
    barcode,
    wbVendorCode: null,
    wbBarcode,
    wbSize: null,
    photoUrl: null,
    expected: 1,
    actual: null,
    delta: null,
    surplus: 0,
    shortage: 0,
    mismatchLeaves: 0,
    leaves: 0,
    countedLeaves: 0,
    expandable: false,
    expanded: false,
    empty: false,
    parentKey: null,
    stale: false,
  }
}

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  root = null
  host?.remove()
  host = null
})

describe('WMS-598 inventory barcode column', () => {
  it('renders the actual generic code for WB alias and Ozon, WB fallback, and blank without a code', async () => {
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
    await act(async () => {
      root!.render(
        <InventoryTree
          rows={[
            product('wb-canonical', 'WB-CANONICAL-598', 'WB-CANONICAL-598'),
            product('wb-alias', 'WB-ALIAS-598', null),
            product('ozon', 'OZN-598-TABLE', null),
            product('wb-legacy-fallback', null, 'WB-LEGACY-598'),
            product('no-code', null, null),
          ]}
          loading={false}
          readOnly={false}
          onToggle={() => {}}
          onActual={() => {}}
        />,
      )
    })

    const barcodeCell = (id: string) => {
      const row = host!.querySelector(`[data-row-key="product:${id}"]`)
      if (!row) throw new Error(`missing row ${id}`)
      return row.querySelectorAll('td')[3]?.textContent ?? ''
    }

    expect(barcodeCell('wb-canonical')).toBe('WB-CANONICAL-598')
    expect(barcodeCell('wb-alias')).toBe('WB-ALIAS-598')
    expect(barcodeCell('ozon')).toBe('OZN-598-TABLE')
    expect(barcodeCell('wb-legacy-fallback')).toBe('WB-LEGACY-598')
    expect(barcodeCell('no-code')).toBe('')
  })
})
