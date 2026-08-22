import { describe, expect, it } from 'vitest'
import { aggregateSources, sourceBreakdown } from './FbsSupplyCreateDialog'
import { ordersWord } from './fbsUx'

const line = {
  product_id: 'product-1',
  product_name: 'Товар 1',
  required: 10,
  current: 0,
  total: 10,
  shortage: 0,
  source_warehouse: { id: 'south', name: 'Склад Юг', available: 6 },
}

describe('FBS supply creation copy', () => {
  it('TC-FBS-UX-001 uses correct Russian order forms', () => {
    expect([1, 2, 4, 5, 11, 21, 22, 25].map((count) => `${count} ${ordersWord(count)}`)).toEqual([
      '1 заказ',
      '2 заказа',
      '4 заказа',
      '5 заказов',
      '11 заказов',
      '21 заказ',
      '22 заказа',
      '25 заказов',
    ])
  })

  it('TC-S17-006 limits the named source by its available stock', () => {
    expect(sourceBreakdown(line)).toBe('Склад Юг · 6; другие склады · 4')
    expect(aggregateSources([line])).toBe('Склад Юг — 6 шт., другие склады — 4 шт.')
  })

  it('TC-S17-006 aggregates repeated source warehouses without overstating them', () => {
    expect(aggregateSources([
      line,
      {
        ...line,
        product_id: 'product-2',
        required: 5,
        current: 1,
        source_warehouse: { id: 'south', name: 'Склад Юг', available: 4 },
      },
    ])).toBe('Склад Юг — 10 шт., другие склады — 4 шт.')
  })
})
