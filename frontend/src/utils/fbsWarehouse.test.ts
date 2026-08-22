import { describe, expect, it } from 'vitest'
import { chooseWarehouseId, operationalWarehouses } from './fbsWarehouse'

const north = { id: 'north', name: 'Север', code: 'north', is_operational: true }
const south = { id: 'south', name: 'Юг', code: 'south', is_operational: true }

describe('fbs warehouse selection', () => {
  it('selects the only operational warehouse', () => {
    expect(chooseWarehouseId([north], null, null)).toBe('north')
  })

  it('selects a marked primary warehouse instead of response order', () => {
    expect(chooseWarehouseId([north, { ...south, is_primary: true }], null, null)).toBe('south')
  })

  it('requires an explicit choice when multiple warehouses have no primary', () => {
    expect(chooseWarehouseId([north, south], null, null)).toBeNull()
  })

  it('restores the warehouse selected earlier in the same session', () => {
    expect(chooseWarehouseId([north, south], null, 'south')).toBe('south')
  })

  it('does not restore a warehouse that is absent from the current operational list', () => {
    expect(chooseWarehouseId([north], null, 'foreign')).toBe('north')
  })

  it('excludes legacy FBS WB warehouses from operational choices', () => {
    expect(
      operationalWarehouses([
        north,
        { id: 'legacy', name: 'FBS WB Москва', code: 'fbs-wb-moscow' },
      ]),
    ).toEqual([north])
  })
})
