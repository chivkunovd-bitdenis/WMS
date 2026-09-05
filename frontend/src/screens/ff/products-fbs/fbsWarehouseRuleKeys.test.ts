import { describe, expect, it } from 'vitest'
import {
  qualifyWarehouseRuleValues,
  warehouseNumberFromRuleKey,
  warehouseRuleKey,
} from './fbsWarehouseRuleKeys'

describe('marketplace-qualified warehouse rule keys', () => {
  const bindings = [
    { marketplace: 'wb' as const, wb_warehouse_id: 123 },
    { marketplace: 'ozon' as const, wb_warehouse_id: 123 },
  ]

  it('keeps both editor rows and their saved quantities distinct', () => {
    expect(bindings.map(warehouseRuleKey)).toEqual(['wb:123', 'ozon:123'])
    expect(qualifyWarehouseRuleValues({ 'wb:123': 20, 'ozon:123': 30 }, bindings))
      .toEqual({ 'wb:123': 20, 'ozon:123': 30 })
    expect(warehouseNumberFromRuleKey('ozon:123')).toBe('123')
    expect(warehouseNumberFromRuleKey('wb:123')).toBe('123')
  })

  it('resolves a legacy numeric response only through its saved binding', () => {
    expect(qualifyWarehouseRuleValues({ 123: 40 }, [bindings[1]!]))
      .toEqual({ 'ozon:123': 40 })
    expect(warehouseNumberFromRuleKey('123')).toBe('123')
    expect(() => qualifyWarehouseRuleValues({ 123: 40 }, bindings)).toThrow('площадку')
  })
})
