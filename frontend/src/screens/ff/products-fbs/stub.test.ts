import { describe, expect, it } from 'vitest'
import { servedWarehouses, splitAmounts } from './stub'
import type { FbsRule, Seller } from './stub'

// Порядок обхода складов решает, кому не хватит свободного остатка, и должен
// совпадать с серверным (`_seller_bindings`: номер, затем площадка). Ключ
// строки приходит с приставкой площадки, поэтому сравнивать его как число
// целиком нельзя — иначе все склады равны между собой и порядок задаёт список.
const seller: Seller = {
  id: 's-1',
  name: 'Продавец',
  warehouses: [
    { id: 'wb:777', name: 'Второй', boundTo: 'w-1', fbsEnabled: true, marketplace: 'wb' },
    { id: 'wb:123', name: 'Первый', boundTo: 'w-1', fbsEnabled: true, marketplace: 'wb' },
    { id: 'ozon:123', name: 'Озон', boundTo: 'w-1', fbsEnabled: true, marketplace: 'ozon' },
  ],
  wbWarehouses: [],
}

describe('обход складов при раздаче остатка', () => {
  it('идёт по номеру склада, а не по порядку в списке', () => {
    expect(servedWarehouses(seller).map((one) => one.id)).toEqual(['ozon:123', 'wb:123', 'wb:777'])
  })

  it('обрезает по свободному остатку последний склад в этом порядке', () => {
    const rule: FbsRule = {
      productId: 'p-1',
      publish: true,
      sameEverywhere: false,
      percent: 0,
      byWarehouse: {},
      unitsMode: true,
      unitsByWarehouse: { 'ozon:123': 4, 'wb:123': 5, 'wb:777': 6 },
    }
    expect(splitAmounts(rule, 10, servedWarehouses(seller)))
      .toEqual({ 'ozon:123': 4, 'wb:123': 5, 'wb:777': 1 })
  })
})
