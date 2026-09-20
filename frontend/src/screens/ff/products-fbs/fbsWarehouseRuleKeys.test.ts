import { describe, expect, it } from 'vitest'
import {
  qualifyWarehouseRuleValues,
  warehouseNumberFromRuleKey,
  warehouseRuleKey,
  warehouseUnitsAfterInput,
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

// Ноль и пустое поле означают на сервере разное: ноль — лимит, который оператор
// поставил сам, пустое — что привязку поштучно не настраивали. Свернуть их
// обратно в один ноль нельзя: тогда склады, которых оператор не касался, уедут
// как явный нулевой лимит.
describe('поштучный лимит склада', () => {
  it('различает явный ноль оператора и незаданный склад', () => {
    expect(warehouseUnitsAfterInput({}, 'wb:1', 0)).toEqual({ 'wb:1': 0 })
    expect(warehouseUnitsAfterInput({ 'wb:1': 7, 'wb:2': 3 }, 'wb:1', null)).toEqual({ 'wb:2': 3 })
  })
})
