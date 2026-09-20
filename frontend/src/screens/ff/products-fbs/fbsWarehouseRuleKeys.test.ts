import { describe, expect, it } from 'vitest'
import {
  qualifyWarehouseRuleValues,
  qualifyWbWarehouseRuleValues,
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

// Экран остатка FBS показывает только склады Wildberries, а правило приходит с
// ключами обеих площадок. Когда у продавца склад Ozon с тем же номером, сервер
// присылает wb:123 — и строка, знавшая себя как «123», показывала пустое поле,
// заводила второй ключ на тот же склад и не могла очистить прежний.
describe('ключи правила на экране остатка FBS', () => {
  const wbNumbers = new Set(['123', '777'])

  it('сводит строку склада и сохранённый лимит к одному ключу', () => {
    expect(qualifyWbWarehouseRuleValues({ 'wb:123': 0, 'ozon:123': 5 }, wbNumbers))
      .toEqual({ 'wb:123': 0, 'ozon:123': 5 })
    expect(qualifyWbWarehouseRuleValues({ 123: 0, 777: 4 }, wbNumbers))
      .toEqual({ 'wb:123': 0, 'wb:777': 4 })
  })

  it('не присваивает Wildberries чужой номер склада', () => {
    expect(qualifyWbWarehouseRuleValues({ 999: 12 }, wbNumbers)).toEqual({ 999: 12 })
  })

  it('после приведения ключей очистка поля убирает настоящий лимит склада', () => {
    const units = qualifyWbWarehouseRuleValues({ 'wb:123': 0, 'ozon:123': 5 }, wbNumbers)
    expect(warehouseUnitsAfterInput(units, 'wb:123', null)).toEqual({ 'ozon:123': 5 })
  })
})
