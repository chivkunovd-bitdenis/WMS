// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildFboBulkSeparatorSection,
  buildFboBulkTapeSections,
  countFboBulkSections,
  groupFboBulkLinesByProduct,
  type FboBulkGroup,
  type FboBulkLineInput,
} from './fboBulkTape'

// Keep both tape builders real so the preview path exercises exactly the
// production code — the review marked a mocked core as unacceptable. We only
// shim the two renderers that need a real browser canvas: the thermal
// barcode (returned as a stub data URL) and bwip-js's `toCanvas` (which
// invokes `raw` so an empty CIS still throws the way bwip-js does in prod,
// but needs no 2D context). `HTMLCanvasElement.toDataURL` is also stubbed
// because jsdom returns an empty string from an unprinted canvas.
vi.mock('./renderBarcodeDataUrl', () => ({
  renderBarcodeDataUrl: () => 'data:image/png;base64,BARCODE',
}))
vi.mock('bwip-js', () => {
  const toCanvas = (canvas: HTMLCanvasElement, options: { bcid?: string; text?: string }) => {
    // Reproduce bwip-js' input validation (same error you get in prod when
    // a line has no CIS or empty barcode): if the review regression ever
    // reintroduces fake-cis plumbing, this test will fail with the exact
    // production error instead of a silent canvas draw.
    if (!options || !options.text) {
      throw new Error('bwipp.undefinedText: bar code text not specified')
    }
    return canvas
  }
  return { default: { toCanvas }, toCanvas }
})
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,MATRIX')
})

const makeLabel = (barcode = '4600000000024') => ({
  product_name: 'Product',
  sku_code: 'SKU-X',
  barcode,
})

const makeLine = (p: Partial<FboBulkLineInput> & { productId: string }): FboBulkLineInput => ({
  lineId: `${p.productId}-${p.lineId ?? 'L1'}`,
  productId: p.productId,
  productName: p.productName ?? p.productId,
  skuCode: p.skuCode ?? p.productId,
  requiresHonestSign: p.requiresHonestSign ?? true,
  qtyNeedPack: p.qtyNeedPack ?? 1,
  productLabel: p.productLabel ?? makeLabel(p.productId),
})

const czLabelLayout = {
  units: [
    { block: 'cz' as const, copies: 1 },
    { block: 'label' as const, copies: 1 },
  ],
}

describe('WMS-618 FBO bulk grouping', () => {
  it('groups lines by product_id in order of first appearance (R6)', () => {
    const groups = groupFboBulkLinesByProduct([
      makeLine({ productId: 'product-A', lineId: 'A1' }),
      makeLine({ productId: 'product-B', lineId: 'B1' }),
      makeLine({ productId: 'product-A', lineId: 'A2' }),
    ])
    expect(groups.map((g) => g.productId)).toEqual(['product-A', 'product-B'])
    expect(groups[0]!.lines.map((l) => l.lineId)).toEqual(['product-A-A1', 'product-A-A2'])
    expect(groups[1]!.lines.map((l) => l.lineId)).toEqual(['product-B-B1'])
  })

  it('keeps duplicate product_id in a single group across different cells', () => {
    const groups = groupFboBulkLinesByProduct([
      makeLine({ productId: 'product-A', lineId: 'cell1', qtyNeedPack: 2 }),
      makeLine({ productId: 'product-A', lineId: 'cell2', qtyNeedPack: 3 }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.lines.reduce((s, l) => s + l.qtyNeedPack, 0)).toBe(5)
  })
})

describe('WMS-618 FBO bulk section count', () => {
  const makeGroup = (id: string, lines: Array<{ qty: number; cz: boolean }>): FboBulkGroup => ({
    productId: id,
    productName: id,
    skuCode: id,
    productLabel: makeLabel(id),
    lines: lines.map((l, i) =>
      makeLine({
        productId: id,
        lineId: `${id}-${i}`,
        qtyNeedPack: l.qty,
        requiresHonestSign: l.cz,
      }),
    ),
  })

  it('counts cz+label blocks per unit for honest-sign lines (R3+R5)', () => {
    const groups = [makeGroup('A', [{ qty: 2, cz: true }])]
    // 2 units × (1 cz + 1 label) = 4 sections
    expect(countFboBulkSections(czLabelLayout, groups, false)).toBe(4)
  })

  it('ignores cz blocks for non-honest-sign lines but keeps label blocks (R3)', () => {
    const groups = [makeGroup('A', [{ qty: 3, cz: false }])]
    expect(countFboBulkSections(czLabelLayout, groups, false)).toBe(3)
  })

  it('counts zero sections when wb-only layout meets no-cz product and WB qty=0 (R5)', () => {
    const groups = [makeGroup('A', [{ qty: 2, cz: false }])]
    const czOnly = { units: [{ block: 'cz' as const, copies: 1 }] }
    expect(countFboBulkSections(czOnly, groups, false)).toBe(0)
  })

  it('inserts separators only between non-empty groups (R5)', () => {
    const groups = [
      makeGroup('A', [{ qty: 1, cz: true }]),
      makeGroup('B', [{ qty: 1, cz: true }]),
      makeGroup('C', [{ qty: 1, cz: true }]),
    ]
    // 3 groups × (1 cz + 1 label) + 2 separators
    expect(countFboBulkSections(czLabelLayout, groups, true)).toBe(8)
  })

  it('no leading or trailing separator; no separator when split=off', () => {
    const groups = [
      makeGroup('A', [{ qty: 2, cz: true }]),
      makeGroup('B', [{ qty: 2, cz: true }]),
    ]
    expect(countFboBulkSections(czLabelLayout, groups, false)).toBe(8)
  })

  it('skips empty groups when counting separators', () => {
    const groups = [
      makeGroup('A', [{ qty: 1, cz: true }]),
      makeGroup('B', [{ qty: 0, cz: true }]), // empty — skipped
      makeGroup('C', [{ qty: 1, cz: true }]),
    ]
    expect(countFboBulkSections(czLabelLayout, groups, true)).toBe(5)
  })
})

describe('WMS-618 FBO bulk separator section', () => {
  it('is a label-sized blank section without barcode or data matrix', () => {
    const html = buildFboBulkSeparatorSection()
    expect(html).toContain('data-testid="fbo-bulk-separator"')
    expect(html).toContain('data-tape-block="separator"')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('Честный')
  })
})

describe('WMS-618 FBO bulk shared tape builder (preview ↔ print)', () => {
  const makeGroup = (id: string, lines: Array<{ qty: number; cz: boolean }>): FboBulkGroup => ({
    productId: id,
    productName: id,
    skuCode: id,
    productLabel: makeLabel(id),
    lines: lines.map((l, i) =>
      makeLine({
        productId: id,
        lineId: `${id}-${i}`,
        qtyNeedPack: l.qty,
        requiresHonestSign: l.cz,
      }),
    ),
  })

  it('builds sections with stub cis when no codes are supplied (preview mode)', async () => {
    const groups = [makeGroup('A', [{ qty: 2, cz: true }])]
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czLabelLayout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      previewCis: (i) => `preview-${i}`,
    })
    expect(sections.length).toBe(4) // 2 units × (cz + label)
  })

  it('builds sections from issued codes when supplied (print mode)', async () => {
    const groups = groupFboBulkLinesByProduct([
      makeLine({ productId: 'A', lineId: 'A1', qtyNeedPack: 2 }),
    ])
    const codes = new Map([
      [
        'A-A1',
        [
          { id: 'c1', cisCode: '01GTIN21SER1', hasLabelArtifact: false },
          { id: 'c2', cisCode: '01GTIN21SER2', hasLabelArtifact: false },
        ],
      ],
    ])
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czLabelLayout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      codesByLineId: codes,
    })
    expect(sections.length).toBe(4)
    expect(sections.filter((s) => s.includes('data-tape-block="cz"'))).toHaveLength(2)
  })

  it('respects maxUnits (preview mode caps tape to 3 units)', async () => {
    const groups = [makeGroup('A', [{ qty: 10, cz: true }])]
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czLabelLayout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      previewCis: (i) => `p-${i}`,
      maxUnits: 3,
    })
    expect(sections.length).toBe(6) // 3 units × (cz + label)
  })

  it('R3/C2: separate CZ tape emits 84 sections for 28 eligible units × 3 copies', async () => {
    const groups = [makeGroup('A', [{ qty: 28, cz: true }])]
    const layout = { units: [{ block: 'cz' as const, copies: 3 }] }
    const sections = await buildFboBulkTapeSections({
      groups, layout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      previewCis: (i) => `preview-${i}`,
    })
    expect(sections).toHaveLength(84)
    expect(countFboBulkSections(layout, groups, false)).toBe(sections.length)
  })

  it('R3/C2: mixed separate CZ tape counts one eligible unit, not both units', async () => {
    const groups = [makeGroup('A', [{ qty: 1, cz: true }]), makeGroup('B', [{ qty: 1, cz: false }])]
    const layout = { units: [{ block: 'cz' as const, copies: 1 }] }
    const sections = await buildFboBulkTapeSections({
      groups, layout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: true,
      previewCis: (i) => `preview-${i}`,
    })
    expect(sections).toHaveLength(1)
    expect(countFboBulkSections(layout, groups, true)).toBe(sections.length)
  })

  it('R3/C2: no-CZ tape emits six blocks for three units × two WB labels', async () => {
    const groups = [makeGroup('A', [{ qty: 3, cz: false }])]
    const layout = { units: [{ block: 'label' as const, copies: 2 }] }
    const sections = await buildFboBulkTapeSections({
      groups, layout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
    })
    expect(sections).toHaveLength(6)
    expect(countFboBulkSections(layout, groups, false)).toBe(sections.length)
  })

  it('duplicate product_id across lines/cells stays in one group with no inner separator', async () => {
    const groups = groupFboBulkLinesByProduct([
      makeLine({ productId: 'A', lineId: 'cell1', qtyNeedPack: 1 }),
      makeLine({ productId: 'A', lineId: 'cell2', qtyNeedPack: 1 }),
      makeLine({ productId: 'B', lineId: 'onlyB', qtyNeedPack: 1 }),
    ])
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czLabelLayout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: true,
      previewCis: (i) => `p-${i}`,
    })
    // 3 units × (cz + label) + 1 separator between A and B
    expect(sections.length).toBe(7)
    const separators = sections.filter((s) => s.includes('fbo-bulk-separator'))
    expect(separators.length).toBe(1)
  })

  it('zero WB qty = zero WB sections even for a non-CZ product', async () => {
    const groups = [
      {
        productId: 'A',
        productName: 'A',
        skuCode: 'A',
        productLabel: makeLabel('A'),
        lines: [makeLine({ productId: 'A', qtyNeedPack: 3, requiresHonestSign: false })],
      },
    ]
    const czOnly = { units: [{ block: 'cz' as const, copies: 1 }] }
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czOnly,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      previewCis: (i) => `p-${i}`,
    })
    expect(sections.length).toBe(0)
  })

  // R8 (P2 regression on fe8c9e7b): the preview budget `maxUnits` must only
  // decrement for units that actually produce sections. Previously a non-CZ
  // line hitting a CZ-only layout burned the budget without emitting anything,
  // which could hide the whole next group from the preview even though the
  // real print would emit it.
  it('R8: preview budget is not burned by filtered-out units (non-CZ + cz-only layout)', async () => {
    const groups = [
      {
        productId: 'A',
        productName: 'A',
        skuCode: 'A',
        productLabel: makeLabel('A'),
        lines: [makeLine({ productId: 'A', qtyNeedPack: 3, requiresHonestSign: false })],
      },
      {
        productId: 'B',
        productName: 'B',
        skuCode: 'B',
        productLabel: makeLabel('B'),
        lines: [makeLine({ productId: 'B', qtyNeedPack: 1, requiresHonestSign: true })],
      },
    ]
    const czOnly = { units: [{ block: 'cz' as const, copies: 2 }] }
    const previewSections = await buildFboBulkTapeSections({
      groups,
      layout: czOnly,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: true,
      previewCis: (i) => `p-${i}`,
      maxUnits: 3,
    })
    // Full print (no budget) emits 2 CZ sections for B and nothing for A.
    const fullSections = await buildFboBulkTapeSections({
      groups,
      layout: czOnly,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: true,
      previewCis: (i) => `p-${i}`,
    })
    expect(fullSections.length).toBe(2)
    // Preview must match: no leading separator because group A is empty.
    expect(previewSections.length).toBe(2)
    expect(previewSections.filter((s) => s.includes('fbo-bulk-separator'))).toHaveLength(0)
  })

  // Mirror case: non-CZ group follows a CZ group; label-only layout. The CZ
  // group burns the budget legitimately, but the non-CZ group must still fit
  // within its remaining budget.
  it('R8: label-only layout emits labels for every group within budget', async () => {
    const groups = [
      {
        productId: 'A',
        productName: 'A',
        skuCode: 'A',
        productLabel: makeLabel('A'),
        lines: [makeLine({ productId: 'A', qtyNeedPack: 1, requiresHonestSign: true })],
      },
      {
        productId: 'B',
        productName: 'B',
        skuCode: 'B',
        productLabel: makeLabel('B'),
        lines: [makeLine({ productId: 'B', qtyNeedPack: 1, requiresHonestSign: false })],
      },
    ]
    const labelOnly = { units: [{ block: 'label' as const, copies: 2 }] }
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: labelOnly,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: true,
      previewCis: (i) => `p-${i}`,
    })
    // A: 1 unit × 2 label = 2; separator; B: 1 unit × 2 label = 2; total = 5
    expect(sections.length).toBe(5)
    expect(sections.filter((s) => s.includes('fbo-bulk-separator'))).toHaveLength(1)
  })

  it('mixed shipment: CZ line gets cz+label blocks, non-CZ line gets only label blocks (R3)', async () => {
    const groups = [
      {
        productId: 'A',
        productName: 'A',
        skuCode: 'A',
        productLabel: makeLabel('A'),
        lines: [makeLine({ productId: 'A', qtyNeedPack: 1, requiresHonestSign: true })],
      },
      {
        productId: 'B',
        productName: 'B',
        skuCode: 'B',
        productLabel: makeLabel('B'),
        lines: [makeLine({ productId: 'B', qtyNeedPack: 1, requiresHonestSign: false })],
      },
    ]
    const sections = await buildFboBulkTapeSections({
      groups,
      layout: czLabelLayout,
      labelSize: { id: '58x40', label: '58 × 40 мм', widthMm: 58, heightMm: 40 },
      splitArticles: false,
      previewCis: (i) => `p-${i}`,
    })
    // A: 1 cz + 1 label = 2 sections; B: 1 label = 1 section; total = 3
    expect(sections.length).toBe(3)
  })
})
