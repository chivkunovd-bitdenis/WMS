import type { MarketplaceCode } from './stub'

export type WarehouseRuleBinding = {
  wb_warehouse_id: number | string
  marketplace?: MarketplaceCode
}

// Привязки, по которым сервер собирает правило: действующие, обеих площадок.
// Снятое «обслуживаем» привязку не отменяет — такой склад не показывается
// строкой окна, но свой номер в правиле по-прежнему занимает.
export function activeRuleBindings(
  rows: Array<{
    wb_warehouse_id: number | string
    marketplace?: MarketplaceCode
    is_active: boolean
  }>,
): WarehouseRuleBinding[] {
  return rows
    .filter((one) => one.is_active)
    .map((one) => ({ wb_warehouse_id: one.wb_warehouse_id, marketplace: one.marketplace ?? 'wb' }))
}

export function warehouseRuleKey(warehouse: WarehouseRuleBinding): string {
  return `${warehouse.marketplace ?? 'wb'}:${warehouse.wb_warehouse_id}`
}

export function warehouseNumberFromRuleKey(key: string): string {
  return key.includes(':') ? key.slice(key.indexOf(':') + 1) : key
}

// Поштучный лимит склада после ввода в поле окна остатка. Очищенное поле
// убирает ключ, а не кладёт ноль: отсутствие ключа сервер читает как «привязку
// поштучно не настраивали», а ноль — как заданный оператором лимит 0 шт.
export function warehouseUnitsAfterInput(
  units: Record<string, number>,
  warehouseId: string,
  value: number | null,
): Record<string, number> {
  const next = { ...units }
  if (value === null) delete next[warehouseId]
  else next[warehouseId] = Math.max(0, value)
  return next
}

// Правило в терминах строк окна остатка. Строка всегда знает свою площадку, а
// сервер называет склад голым номером, пока номер уникален среди АКТИВНЫХ
// привязок продавца, и переходит на wb:<номер> / ozon:<номер>, когда номера
// совпали. Без приведения ключей сохранённый лимит показывался бы пустым полем,
// введённый заново уехал бы вторым ключом на тот же склад, а очистка не убрала
// бы прежний.
//
// Площадку номера берём из действующих привязок обеих площадок: справочник
// складов кабинета Wildberries помнит и отключённую привязку, и по нему номер
// 123 выглядел бы вайлдберрисовским даже тогда, когда активен с этим номером
// один лишь склад Ozon.
//
// Неразрешимый номер — отказ: экран сообщает об ошибке загрузки и не открывает
// правку. Молча отдать правило как есть нельзя — строка склада показывала бы
// пустое поле вместо сохранённого лимита, введённое рядом уехало бы вторым
// ключом на тот же склад, а очистка оставила бы прежний невидимым.
export function ruleKeysForScreen<T extends {
  byWarehouse: Record<string, number>
  unitsByWarehouse: Record<string, number>
}>(rule: T, bindings: WarehouseRuleBinding[]): T {
  return {
    ...rule,
    byWarehouse: qualifyWarehouseRuleValues(rule.byWarehouse, bindings),
    unitsByWarehouse: qualifyWarehouseRuleValues(rule.unitsByWarehouse, bindings),
  }
}

/** Legacy numeric responses are resolved against saved bindings, never by row order. */
export function qualifyWarehouseRuleValues(
  values: Record<string, number>,
  bindings: WarehouseRuleBinding[],
): Record<string, number> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => {
    if (key.includes(':')) return [key, value]
    const matches = bindings.filter((binding) => String(binding.wb_warehouse_id) === key)
    if (matches.length !== 1) {
      throw new Error(`Не удалось определить площадку склада ${key}. Обновите список складов.`)
    }
    return [warehouseRuleKey(matches[0]!), value]
  }))
}
