import type { MarketplaceCode } from './stub'

export type WarehouseRuleBinding = {
  wb_warehouse_id: number | string
  marketplace?: MarketplaceCode
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

// Экран «Остаток для FBS» показывает только склады Wildberries, и его строки
// живут под ключом wb:<номер>. Сервер же называет тот же склад голым номером,
// пока номер уникален, и переходит на wb:<номер> ровно тогда, когда у продавца
// есть озоновский склад с тем же числом. Без приведения ключей сохранённый
// лимит такого склада выглядел бы пустым полем, введённый заново уехал бы
// вторым ключом на тот же склад, а очистка поля не убрала бы прежний.
//
// Голый номер, которого нет среди привязанных складов WB этого продавца, не
// трогаем: он принадлежит другой площадке, и вернуть его серверу нужно ровно
// таким, каким он пришёл.
export function qualifyWbWarehouseRuleValues(
  values: Record<string, number>,
  boundWbWarehouseNumbers: ReadonlySet<string>,
): Record<string, number> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => {
    const qualified = warehouseRuleKey({ wb_warehouse_id: key })
    const belongsToWb =
      !key.includes(':') && boundWbWarehouseNumbers.has(key) && values[qualified] === undefined
    return [belongsToWb ? qualified : key, value]
  }))
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
