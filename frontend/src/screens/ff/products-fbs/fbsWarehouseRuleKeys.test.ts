import { describe, expect, it } from 'vitest'
import {
  activeRuleBindings,
  qualifyWarehouseRuleValues,
  ruleKeysForScreen,
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
// ключами обеих площадок и с голыми номерами. Строка знает себя как wb:123,
// поэтому без приведения ключей сохранённый лимит показывался бы пустым полем,
// введённый заново уехал бы вторым ключом на тот же склад, а очистка не убрала
// бы прежний.
describe('ключи правила на экране остатка FBS', () => {
  const rule = (unitsByWarehouse: Record<string, number>) => ({
    productId: 'p-1',
    publish: true,
    sameEverywhere: false,
    percent: 0,
    unitsMode: true,
    byWarehouse: {},
    unitsByWarehouse,
  })

  // Тот самый случай, ради которого площадку определяем по привязкам, а не по
  // справочнику складов кабинета: отключённая привязка остаётся в справочнике
  // сопоставленной, и её номер забирал себе озоновский лимит. Окно показывало
  // чужое число, а сохранение падало с «склад не найден».
  it('не отдаёт номер отключённой привязки складу Wildberries', () => {
    const bindings = activeRuleBindings([
      { marketplace: 'wb', wb_warehouse_id: 123, is_active: false },
      { marketplace: 'ozon', wb_warehouse_id: 123, is_active: true },
      { marketplace: 'wb', wb_warehouse_id: 777, is_active: true },
    ])
    expect(ruleKeysForScreen(rule({ 123: 5, 777: 0 }), bindings).unitsByWarehouse)
      .toEqual({ 'ozon:123': 5, 'wb:777': 0 })
  })

  it('считает привязкой и склад, который перестали обслуживать', () => {
    expect(activeRuleBindings([
      { wb_warehouse_id: 777, is_active: true },
      { marketplace: 'ozon', wb_warehouse_id: 123, is_active: true },
      { marketplace: 'wb', wb_warehouse_id: 123, is_active: false },
    ])).toEqual([
      { wb_warehouse_id: 777, marketplace: 'wb' },
      { wb_warehouse_id: 123, marketplace: 'ozon' },
    ])
  })

  it('разводит активные склады с одинаковым номером и хранит озоновский лимит', () => {
    const bindings = activeRuleBindings([
      { marketplace: 'wb', wb_warehouse_id: 123, is_active: true },
      { marketplace: 'ozon', wb_warehouse_id: 123, is_active: true },
    ])
    const units = ruleKeysForScreen(rule({ 'wb:123': 0, 'ozon:123': 5 }), bindings).unitsByWarehouse
    expect(units).toEqual({ 'wb:123': 0, 'ozon:123': 5 })
    // Правку строки Wildberries и её очистку окно ведёт по ключу wb:123, а
    // невидимый на этом экране озоновский лимит доезжает до сервера как был.
    expect(warehouseUnitsAfterInput(units, 'wb:123', 4)).toEqual({ 'wb:123': 4, 'ozon:123': 5 })
    expect(warehouseUnitsAfterInput(units, 'wb:123', null)).toEqual({ 'ozon:123': 5 })
  })

  it('оставляет правило как есть, если номер не нашёлся среди привязок', () => {
    const bindings = activeRuleBindings([
      { marketplace: 'wb', wb_warehouse_id: 777, is_active: true },
    ])
    expect(ruleKeysForScreen(rule({ 999: 12, 777: 3 }), bindings).unitsByWarehouse)
      .toEqual({ 999: 12, 777: 3 })
  })
})
