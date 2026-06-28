import { describe, expect, it } from 'vitest'

import { resolvePackUnits, resolveWbBarcodeLabelCount } from './productBarcodePrint'

describe('resolvePackUnits', () => {
  it('reads explicit pack_units token from packaging instructions', () => {
    expect(resolvePackUnits({ packaging_instructions: 'pack_units:5' })).toBe(5)
    expect(resolvePackUnits({ packaging_instructions: 'ТЗ pack_units=5 для склада' })).toBe(5)
  })

  it('defaults to 1 when pack size is unknown', () => {
    expect(resolvePackUnits({ packaging_instructions: 'E2E: пакет + стикер WB' })).toBe(1)
    expect(resolvePackUnits(null)).toBe(1)
  })
})

describe('resolveWbBarcodeLabelCount', () => {
  // PRINT-04 gate: qty 3 при pack 5 → 15 этикеток.
  it('multiplies qty by pack units', () => {
    expect(resolveWbBarcodeLabelCount(3, 5)).toBe(15)
    expect(resolveWbBarcodeLabelCount(3, 1)).toBe(3)
  })
})
