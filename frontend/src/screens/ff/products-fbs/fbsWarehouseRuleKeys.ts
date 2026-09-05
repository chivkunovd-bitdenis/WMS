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
