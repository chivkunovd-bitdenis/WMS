import { describe, expect, it } from 'vitest'

import { productWarehouseQuantity } from './productsWarehouse'

describe('ProductsScreen warehouse quantities', () => {
  it('reads only the quantity returned for the selected warehouse', () => {
    const northQuantities = { 'product-1': 7 }
    const southQuantities = { 'product-1': 3 }

    expect(productWarehouseQuantity('product-1', northQuantities)).toBe(7)
    expect(productWarehouseQuantity('product-1', southQuantities)).toBe(3)
  })

  it('shows zero for a catalog product absent from the selected warehouse summary', () => {
    expect(productWarehouseQuantity('product-without-balance', {})).toBe(0)
  })
})
