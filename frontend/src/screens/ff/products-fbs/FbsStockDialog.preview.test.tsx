import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { FbsStockDialog } from './FbsStockDialog'
import { toProduct, toRule, type ApiRule } from './FfProductsFbsPage'
import type { Seller } from './stub'
import { warehouseRuleKey } from './fbsWarehouseRuleKeys'

vi.mock('../../../ui-kit', async (original) => ({
  ...await original<object>(),
  // Only remove the portal for SSR; all fields and dialog content are real.
  AppDialog: ({ children, actions }: { children: ReactNode; actions: ReactNode }) =>
    <div>{children}{actions}</div>,
}))
const bindings = [
  { wb_warehouse_id: 123, marketplace: 'wb' as const },
  { wb_warehouse_id: 123, marketplace: 'ozon' as const },
]
const seller: Seller = {
  id: 'seller', name: 'Synthetic', wbWarehouses: [],
  warehouses: bindings.map((binding, i) => ({
    id: warehouseRuleKey(binding), name: binding.marketplace, marketplace: binding.marketplace,
    boundTo: `physical-${i}`, fbsEnabled: true,
  })),
}
const apiRule: ApiRule = {
  publish: true, publish_ozon: true, same_everywhere: true, percent: 50,
  by_warehouse: {}, units_mode: false,
  units_by_warehouse: { 'wb:123': 5, 'ozon:123': 3 },
  units_remaining_by_warehouse: { 'wb:123': 5, 'ozon:123': 3 },
  on_hand: 6, reserved: 0, free_stock: 6, published_now: 2,
}
const row = { id: 'product', seller_id: 'seller', name: 'Synthetic', sku_code: 'SKU',
  wb_primary_barcode: null, marketplaces: ['wb', 'ozon'] }
function render(rule: ApiRule | undefined) {
  return renderToStaticMarkup(<FbsStockDialog open products={[toProduct(row, rule, seller.id)]}
    seller={seller} rule={toRule(row.id, rule, bindings)} onClose={() => {}}
    onSave={() => {}} onBind={() => {}} />)
}

describe('WMS-417 stock namespace and publication display', () => {
  it('keeps WB and Ozon 123 separate and displays stored WB5', () => {
    const mapped = toRule('product', apiRule, bindings)
    expect(mapped.unitsByWarehouse).toEqual({ 'wb:123': 5, 'ozon:123': 3 })
    const markup = render({ ...apiRule, units_mode: true })
    expect(markup).toContain('data-testid="fbs-stock-units-wb:123"')
    expect(markup).toContain('value="5"')
    expect(markup).toContain('value="3"')
  })
  it('qualifies unique legacy numbers but refuses ambiguous numeric 123', () => {
    expect(toRule('product', { ...apiRule, units_by_warehouse: { 123: 5 } }, [bindings[0]!])
      .unitsByWarehouse).toEqual({ 'wb:123': 5 })
    expect(() => toRule('product', { ...apiRule, units_by_warehouse: { 123: 5 } }, bindings))
      .toThrow('площадку')
  })
  it('shows saved server2 for two physical warehouses instead of aggregate draft6', () => {
    const markup = render(apiRule)
    expect(markup).toContain('data-testid="fbs-stock-result">2 шт')
    expect(markup).toContain('по сохранённому правилу')
    expect(markup).toContain('Изменения в этом окне ещё не учтены')
    expect(markup).not.toContain('На этот склад уйдёт')
    expect(markup).not.toContain('прямо сейчас')
    expect(markup).not.toContain('— это 3')
  })
  it('does not invent zero when the API rule is unavailable', () => {
    expect(render(undefined)).toContain('Расчёт публикации недоступен')
  })
})
