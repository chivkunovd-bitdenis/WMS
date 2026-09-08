import { describe, expect, it } from 'vitest'
import { PickScanSourceError, resolveProductScanSource, scanSourceKey } from './pickScanSource'

const product = { id: 'can-product', sku: 'EMU-CAN-PVZ-TRUE' }
const location = {
  storage_location_id: 'FBS-VIDEO-01',
  available: 59,
  sources: [
    { available: 19, container_path: [{ kind: 'pallet' as const, id: 'pallet' }, { kind: 'cargo_place' as const, id: 'cargo' }] },
    { available: 40, container_path: [{ kind: 'pallet' as const, id: 'pallet' }, { kind: 'box' as const, id: 'box' }] },
  ],
}

describe('WMS-058 physical source selection for shared FBS and MP scans', () => {
  it('requires the existing choice for cargo and box in one cell instead of posting loose stock', () => {
    try {
      resolveProductScanSource(product, [location], null)
      expect.fail('ambiguous physical stock must not turn into a loose-stock request')
    } catch (error) {
      expect(error).toBeInstanceOf(PickScanSourceError)
      expect(error).toMatchObject({ productId: product.id })
      expect((error as Error).message).toContain('в 2 местах')
      expect((error as Error).message).not.toContain('Недостаточно')
    }
  })

  it('uses the single available leaf container even when another container has no available units', () => {
    const source = resolveProductScanSource(product, [{ ...location, sources: [
      { ...location.sources[0], available: 0 }, location.sources[1],
    ] }], null)
    expect(source).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })
    expect(scanSourceKey(source)).toBe('obj:box')
  })

  it('preserves explicit container choice without inventing another source', () => {
    const source = resolveProductScanSource(product, [location], { locationId: 'FBS-VIDEO-01', containerKind: 'cargo_place', containerId: 'cargo' })
    expect(source.containerId).toBe('cargo')
    expect(resolveProductScanSource(product, [], { locationId: 'FBS-VIDEO-01', containerKind: 'pallet', containerId: 'pallet' })).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'pallet', containerId: 'pallet' })
  })

  it('keeps loose stock as a null-container request and supports the legacy location contract', () => {
    for (const entry of [
      { storage_location_id: 'cell', available: 1, sources: [{ available: 1, container_path: [] }] },
      { storage_location_id: 'cell', available: 1 },
    ]) {
      const source = resolveProductScanSource(product, [entry], null)
      expect(source).toEqual({ locationId: 'cell', containerKind: null, containerId: null })
      expect(scanSourceKey(source)).toBe('cell:cell')
    }
  })

  it('does not use loose stock when the selected container is exhausted', () => {
    const entry = { ...location, sources: [
      { ...location.sources[1], available: 0 }, { available: 12, container_path: [] },
    ] }
    expect(resolveProductScanSource(product, [entry], { locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })).toEqual({ locationId: 'FBS-VIDEO-01', containerKind: 'box', containerId: 'box' })
  })

  it.each([0, 4])('keeps an explicitly scanned cell as loose stock when loose available is %s', (available) => {
    const selected = { locationId: 'FBS-VIDEO-01', containerKind: null, containerId: null }
    const entry = { ...location, sources: [
      { available, container_path: [] }, location.sources[1],
    ] }
    const source = resolveProductScanSource(product, [entry], selected)
    expect(source).toBe(selected)
    expect(source.containerKind).toBeNull()
    expect(source.containerId).toBeNull()
    expect(scanSourceKey(source)).toBe('cell:FBS-VIDEO-01')
  })

  it('counts physical sources across cells and restricts scanned cell scope', () => {
    const entries = [location, { storage_location_id: 'other-cell', available: 1, sources: [{ available: 1, container_path: [] }] }]
    expect(() => resolveProductScanSource(product, entries, null)).toThrow('в 3 местах')
    expect(resolveProductScanSource(product, entries, { locationId: 'other-cell', containerKind: null, containerId: null })).toEqual({ locationId: 'other-cell', containerKind: null, containerId: null })
  })
})
